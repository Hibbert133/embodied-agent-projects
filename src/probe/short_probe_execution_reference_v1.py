"""Draft visible-only execution for seven standard short-probe references.

Callbacks persist public declarations and execute saved commands. No environment,
seed, actuator truth, native state or future result is accepted. This component
has no physical qualification and does not change the running effect study.
"""
from copy import deepcopy
from dataclasses import asdict

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.chronological_cache_reference import BLOCK8, BALANCED8, budget_valid
from src.probe.cold_start_response import ColdPrefix, TASKS, infer_operator, validate_model
from src.probe.continuous import StepObservation
from src.probe.forward_prediction import vector
from src.probe.operator_identification import affine_controller, encode_controller, identity_controller
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.short_probe_design_reference_v1 import design_four


METHODS = ('NO_PROBE', 'ORIGINAL8_UPDATE', 'BALANCED4_UPDATE', 'DOPT4_UPDATE',
           'DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8')
DOPT_METHODS = METHODS[3:]


def ended(current):
    return current.success or current.terminated or current.truncated


def execute_reference(method, task, initial, model, policy, step, emit, *, design=None, remaining_budget=500):
    """Execute once from a declared live controlled-reset boundary.

    A future host must independently enforce its actual zero-step boundary,
    continuous noise/time, budget and persistence. DOPT artifacts are checked
    against the full nominal-only computation before the first command; these
    repeated verification computations are explicitly counted, not hidden.
    """
    if method not in METHODS or task not in TASKS:
        raise ValueError('registered method and task required')
    if type(initial) is not StepObservation or ended(initial):
        raise ValueError('live controlled initial observation required')
    vector(initial.observation, 39)
    if type(remaining_budget) is not int or not 0 < remaining_budget <= 500:
        raise ValueError('positive integer remaining budget within 500 required')
    if not all(callable(value) for value in (policy, step, emit)):
        raise ValueError('policy, persistence and live step callbacks required')
    design_candidates = 0
    if method == 'NO_PROBE':
        if model is not None or design is not None:
            raise ValueError('uncorrected reference has no model or design dependency')
        model_hash = design_hash = None
        program = []
    else:
        validate_model(model)
        model = normalize(model)
        if model['task'] != task:
            raise ValueError('task-specific nominal model required')
        model_hash = digest(normalize(model));design_hash = None
        if method in DOPT_METHODS:
            if type(design) is not dict:
                raise ValueError('saved nominal design artifact required')
            artifact = normalize(design);expected = design_four(model)
            if digest(artifact) != digest(normalize(expected)) or expected['selected_candidate_id'] is None:
                raise ValueError('saved design differs from nominal computation or is unidentifiable')
            design_candidates = expected['candidate_count'];design_hash = digest(artifact)
            program = next(row['commands'] for row in artifact['candidates']
                           if row['candidate_id'] == artifact['selected_candidate_id'])
        else:
            if design is not None:
                raise ValueError('design artifact is not an input to this reference')
            program = BLOCK8 if method == 'ORIGINAL8_UPDATE' else BALANCED8[:4]
        maximum_probe = 8 if method in ('ORIGINAL8_UPDATE', 'DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8') else 4
        if not budget_valid(remaining_budget, maximum_probe):
            raise ValueError('probe would consume the fixed 32-step task reserve')

    calls = 0;current = initial;trace = [];events = [];fits = [];queries = 0
    commands = [];observations = [];controller = None;decision = None;stopped = False
    last_sequence = -1;last_ns = -1

    def save(event, payload):
        nonlocal last_sequence, last_ns
        declaration = normalize(payload)
        # Keep the expected declaration separate even if a callback mutates its
        # argument in place; clone the acknowledgement before using it later.
        saved = emit(event, deepcopy(declaration))
        if (type(saved) is not dict or set(saved) != set(declaration) | {'sequence', 'saved_ns'} or
            type(saved['sequence']) is not int or saved['sequence'] != last_sequence+1 or
            type(saved['saved_ns']) is not int or saved['saved_ns'] < 0 or saved['saved_ns'] < last_ns or
            digest(normalize({key:saved[key] for key in declaration})) != digest(declaration)):
            raise ValueError('saved public acknowledgement differs')
        last_sequence = saved['sequence'];last_ns = saved['saved_ns']
        saved = normalize(saved);events.append({'event':event, 'public_payload':saved})
        return saved

    def choose(action, **payload):
        return save('CHOICE', {'action':action, 'at_calls':calls, **payload})

    def move(command, phase, choice, raw=None):
        nonlocal calls, current
        if ended(current) or calls >= remaining_budget:
            raise ValueError('ended or exhausted reference stepped')
        sent = np.asarray(vector(command, 4), np.float32)
        if np.any(np.abs(sent) > 1):
            raise ValueError('bounded saved command required')
        request = save('COMMAND', {'at_calls':calls, 'phase':phase, 'decision_sequence':choice['sequence'],
            'command':sent.tolist(), 'raw_policy':None if raw is None else raw.tolist(), 'before':asdict(current)})
        supplied = deepcopy(request);after = step(supplied);calls += 1
        if digest(normalize(supplied)) != digest(request):
            raise ValueError('executor mutated a saved command')
        if type(after) is not StepObservation:
            raise ValueError('public step observation required')
        vector(after.observation, 39)
        trace.append({'logical_step':calls-1, 'phase':phase, 'command':request['command'],
            'raw_policy':request['raw_policy'], 'command_sequence':request['sequence'],
            'decision_sequence':choice['sequence'], 'before':asdict(current), 'after':asdict(after)})
        current = after
        if phase == 'FIXED_PROBE':
            commands.append(tuple(request['command']));observations.append(current.observation)

    def probe(rows, action, **payload):
        if not budget_valid(remaining_budget-calls, len(rows)):
            raise ValueError('probe continuation would consume task reserve')
        choice = choose(action, program=[list(row) for row in rows], **payload)
        for command in choice['program']:
            if ended(current):
                break
            move(command, 'FIXED_PROBE', choice)

    def estimate(count):
        if calls != count or len(commands) != count or ended(current):
            raise ValueError('exact completed live prefix required for fitting')
        prefix = ColdPrefix(task, initial.observation, tuple(commands), tuple(observations), True)
        fit = infer_four(model, prefix) if count == 4 else infer_operator(model, prefix)
        record = save('FIT_RESULT', {'at_calls':calls, 'prefix':asdict(prefix),
            'prefix_evidence_sha256':digest(asdict(prefix)), 'fit':normalize(fit)})
        fits.append(record)
        return record

    def select(record):
        nonlocal controller, decision, stopped
        if record['fit']['valid'] is True:
            selected = affine_controller(record['fit']['matrix_xy'], record['fit']['bias_xy'])
            decision = choose('RUN_FITTED', controller=selected, fit_sequence=record['sequence'],
                              fitted_prefix_steps=record['at_calls'])
            controller = decision['controller']
        else:
            decision = choose('STOP_INVALID_FIT', fit_sequence=record['sequence'])
            controller = None;stopped = True

    save('PROGRAM', {'method':method, 'task':task, 'initial':asdict(initial),
        'remaining_budget':remaining_budget, 'nominal_model_payload_sha256':model_hash,
        'design_evidence_sha256':design_hash, 'design_verification_candidates':design_candidates})
    if method == 'NO_PROBE':
        decision = choose('RUN_IDENTITY', controller=identity_controller());controller = decision['controller']
    elif method == 'ORIGINAL8_UPDATE':
        probe(program, 'PROBE_EIGHT')
        if not ended(current):
            select(estimate(8))
    else:
        probe(program, 'PROBE_FOUR')
        if not ended(current):
            if method == 'DOPT8_UPDATE':
                probe(program, 'COMPLETE_EIGHT')
                if not ended(current):
                    select(estimate(8))
            else:
                four = estimate(4)
                if method == 'DOPT4_KEEP_AT8':
                    probe(program, 'COMPLETE_EIGHT_KEEP_FOUR', fit_sequence=four['sequence'])
                    if not ended(current):
                        select(four)
                elif method == 'DOPT4_FALLBACK8' and four['fit']['valid'] is not True:
                    probe(program, 'COMPLETE_EIGHT_INVALID_FOUR', fit_sequence=four['sequence'])
                    if not ended(current):
                        select(estimate(8))
                else:
                    select(four)

    while not ended(current) and calls < remaining_budget and controller is not None:
        queries += 1
        raw = np.asarray(vector(policy(np.asarray(current.observation).copy()), 4), np.float32)
        move(encode_controller(decision['controller'], raw), 'POLICY', decision, raw)
    reason = ('SUCCESS' if current.success else 'TERMINATED' if current.terminated else
              'TRUNCATED' if current.truncated else 'STOP_INVALID_FIT' if stopped else 'BUDGET_EXHAUSTED')
    outcome = {'success':current.success, 'stopped':stopped, 'end_reason':reason,
        'total_steps':calls, 'deadline_loss':calls if current.success else 500,
        'fixed_probe_steps':len(commands), 'policy_steps':sum(row['phase'] == 'POLICY' for row in trace),
        'online_parameter_fits':len(fits), 'optimizer_nfev':sum(int(record['fit'].get('nfev', 0)) for record in fits),
        'policy_queries':queries, 'applied_fitted_controller':method != 'NO_PROBE' and any(row['phase'] == 'POLICY' for row in trace),
        'design_verification_candidates':design_candidates}
    save('OUTCOME', {'at_calls':calls, 'outcome':outcome, 'final_observation':asdict(current)})
    return normalize({'method':method, 'events':events, 'trace':trace, 'fits':fits, 'outcome':outcome})
