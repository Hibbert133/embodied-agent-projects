"""Draft public-transcript audit, without executing an actor or environment.

This checks the seven fixed programs and recomputes their visible-only fits.
It does not establish real physics, journal authenticity, official policy calls,
the complete population or statistics. Those independent audit layers remain
required. Numerical fit/design/controller helpers are explicitly shared.
"""
from dataclasses import asdict

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.chronological_cache_reference import BLOCK8, BALANCED8
from src.probe.cold_start_response import ColdPrefix, TASKS, infer_operator, validate_model
from src.probe.continuous import StepObservation
from src.probe.forward_prediction import vector
from src.probe.operator_identification import affine_controller, encode_controller, identity_controller
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.short_probe_design_reference_v1 import design_four


METHODS = ('NO_PROBE', 'ORIGINAL8_UPDATE', 'BALANCED4_UPDATE', 'DOPT4_UPDATE',
           'DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8')
DOPT = METHODS[3:]


def same(actual, expected):
    if digest(normalize(actual)) != digest(normalize(expected)):
        raise ValueError('public record differs from registered program or observed history')


def observation(value):
    if type(value) is not dict or set(value) != {'observation', 'success', 'terminated', 'truncated'}:
        raise ValueError('strict public step observation required')
    result = StepObservation(**value);vector(result.observation, 39)
    return result


def audit_public_run(record, task, model, *, design=None):
    """Validate a complete public callback record against the fixed specification."""
    if type(record) is not dict or set(record) != {'method', 'events', 'trace', 'fits', 'outcome'}:
        raise ValueError('complete strict public record required')
    method = record['method']
    if method not in METHODS or task not in TASKS:
        raise ValueError('registered reference and task required')
    if any(type(record[key]) is not list for key in ('events', 'trace', 'fits')):
        raise ValueError('ordered public events, trace and fits required')
    events = record['events'];trace = record['trace']
    previous_time = -1
    for sequence, event in enumerate(events):
        if type(event) is not dict or set(event) != {'event', 'public_payload'} or type(event['public_payload']) is not dict:
            raise ValueError('strict public event envelope required')
        payload = event['public_payload']
        if (type(payload.get('sequence')) is not int or payload['sequence'] != sequence or
            type(payload.get('saved_ns')) is not int or payload['saved_ns'] < 0 or payload['saved_ns'] < previous_time):
            raise ValueError('public event sequence or clock is invalid')
        previous_time = payload['saved_ns']
    if not events or events[0]['event'] != 'PROGRAM':
        raise ValueError('saved initial program required')
    initial = observation(events[0]['public_payload']['initial']);current = initial
    if current.success or current.terminated or current.truncated:
        raise ValueError('live initial controlled boundary required')
    if method == 'NO_PROBE':
        if model is not None or design is not None:
            raise ValueError('uncorrected reference has no nominal dependencies')
        model_hash = design_hash = None;program = [];design_candidates = 0
    else:
        validate_model(model)
        if model['task'] != task:
            raise ValueError('matching frozen task-specific model required')
        model_hash = digest(normalize(model));design_hash = None;design_candidates = 0
        if method in DOPT:
            expected = design_four(model);same(design, expected)
            if expected['selected_candidate_id'] is None:
                raise ValueError('no identifiable saved nominal design')
            program = next(row['commands'] for row in expected['candidates'] if row['candidate_id'] == expected['selected_candidate_id'])
            design_hash = digest(normalize(design));design_candidates = expected['candidate_count']
        else:
            if design is not None:
                raise ValueError('unexpected design dependency')
            program = BLOCK8 if method == 'ORIGINAL8_UPDATE' else BALANCED8[:4]
    position = 0;calls = 0;commands = [];observed = [];fit_records = []
    stopped = False;controller = None;policy_choice = None

    def ended():
        return current.success or current.terminated or current.truncated

    def take(kind, fields):
        nonlocal position
        if position >= len(events) or events[position]['event'] != kind:
            raise ValueError('registered public program event order violated')
        payload = events[position]['public_payload'];position += 1
        if set(payload) != set(fields) | {'sequence', 'saved_ns'}:
            raise ValueError('unknown or missing public payload field')
        if 'at_calls' in fields and (type(payload['at_calls']) is not int or payload['at_calls'] != calls):
            raise ValueError('public event precedes its claimed observations or has a stale clock')
        return payload

    def choice(action, **values):
        expected = {'action':action, 'at_calls':calls, **values}
        row = take('CHOICE', expected)
        same({key:row[key] for key in expected}, expected)
        return row

    def command(phase, selected, fixed=None):
        nonlocal calls, current
        if ended() or calls >= 500 or calls >= len(trace):
            raise ValueError('public command after ending, budget or missing trace')
        row = take('COMMAND', {'at_calls', 'phase', 'decision_sequence', 'command', 'raw_policy', 'before'})
        same(row['phase'], phase);same(row['decision_sequence'], selected['sequence'])
        same(row['before'], asdict(current))
        if phase == 'FIXED_PROBE':
            same(row['raw_policy'], None);expected_command = np.asarray(vector(fixed, 4), np.float32)
        else:
            raw = np.asarray(vector(row['raw_policy'], 4), np.float32)
            same(raw.tolist(), row['raw_policy'])
            expected_command = encode_controller(selected['controller'], raw)
        same(row['command'], expected_command.tolist())
        actual = trace[calls]
        if type(actual) is not dict or set(actual) != {'logical_step', 'phase', 'command', 'raw_policy', 'command_sequence', 'decision_sequence', 'before', 'after'}:
            raise ValueError('strict public transition required')
        same({key:actual[key] for key in ('logical_step', 'phase', 'command', 'raw_policy', 'command_sequence', 'decision_sequence', 'before')},
             {'logical_step':calls, 'phase':phase, 'command':row['command'], 'raw_policy':row['raw_policy'],
              'command_sequence':row['sequence'], 'decision_sequence':selected['sequence'], 'before':row['before']})
        current = observation(actual['after']);calls += 1
        if phase == 'FIXED_PROBE':
            commands.append(tuple(row['command']));observed.append(current.observation)

    def probe(rows, action, **values):
        if len(rows)+32 > 500-calls:
            raise ValueError('public probe consumes registered task reserve')
        selected = choice(action, program=[list(row) for row in rows], **values)
        for value in rows:
            if ended():
                break
            command('FIXED_PROBE', selected, value)

    def estimate(count):
        if calls != count or ended() or len(commands) != count:
            raise ValueError('fit requires exactly the currently observed live prefix')
        row = take('FIT_RESULT', {'at_calls', 'prefix', 'prefix_evidence_sha256', 'fit'})
        prefix = ColdPrefix(task, initial.observation, tuple(commands), tuple(observed), True)
        same(row['prefix'], asdict(prefix));same(row['prefix_evidence_sha256'], digest(asdict(prefix)))
        expected = infer_four(model, prefix) if count == 4 else infer_operator(model, prefix)
        same(row['fit'], normalize(expected));fit_records.append(row)
        return row

    def apply(row):
        nonlocal controller, policy_choice, stopped
        if row['fit']['valid'] is True:
            expected = affine_controller(row['fit']['matrix_xy'], row['fit']['bias_xy'])
            policy_choice = choice('RUN_FITTED', controller=expected, fit_sequence=row['sequence'], fitted_prefix_steps=row['at_calls'])
            controller = expected
        else:
            choice('STOP_INVALID_FIT', fit_sequence=row['sequence']);stopped = True

    first = {'method':method, 'task':task, 'initial':asdict(initial), 'remaining_budget':500,
        'nominal_model_payload_sha256':model_hash, 'design_evidence_sha256':design_hash,
        'design_verification_candidates':design_candidates}
    row = take('PROGRAM', first);same({key:row[key] for key in first}, first)
    if method == 'NO_PROBE':
        controller = identity_controller();policy_choice = choice('RUN_IDENTITY', controller=controller)
    else:
        probe(program, 'PROBE_EIGHT' if method == 'ORIGINAL8_UPDATE' else 'PROBE_FOUR')
        if not ended():
            if method == 'ORIGINAL8_UPDATE':
                apply(estimate(8))
            elif method == 'DOPT8_UPDATE':
                probe(program, 'COMPLETE_EIGHT')
                if not ended():
                    apply(estimate(8))
            else:
                four = estimate(4)
                if method == 'DOPT4_KEEP_AT8':
                    probe(program, 'COMPLETE_EIGHT_KEEP_FOUR', fit_sequence=four['sequence'])
                    if not ended():
                        apply(four)
                elif method == 'DOPT4_FALLBACK8' and four['fit']['valid'] is not True:
                    probe(program, 'COMPLETE_EIGHT_INVALID_FOUR', fit_sequence=four['sequence'])
                    if not ended():
                        apply(estimate(8))
                else:
                    apply(four)
    while not ended() and calls < 500 and controller is not None:
        command('POLICY', policy_choice)
    outcome = {'success':current.success, 'stopped':stopped,
        'end_reason':'SUCCESS' if current.success else 'TERMINATED' if current.terminated else 'TRUNCATED' if current.truncated else 'STOP_INVALID_FIT' if stopped else 'BUDGET_EXHAUSTED',
        'total_steps':calls, 'deadline_loss':calls if current.success else 500,
        'fixed_probe_steps':len(commands), 'policy_steps':calls-len(commands), 'online_parameter_fits':len(fit_records),
        'optimizer_nfev':sum(int(row['fit'].get('nfev', 0)) for row in fit_records),
        'policy_queries':calls-len(commands), 'applied_fitted_controller':method != 'NO_PROBE' and calls > len(commands),
        'design_verification_candidates':design_candidates}
    last = take('OUTCOME', {'at_calls', 'outcome', 'final_observation'})
    same(last['outcome'], outcome);same(last['final_observation'], asdict(current))
    same(record['fits'], fit_records);same(record['outcome'], outcome)
    if position != len(events) or calls != len(trace):
        raise ValueError('unconsumed events or transitions after public ending')
    return {'integrity':'PUBLIC_PROGRAM_CONSISTENT', 'method':method, 'public_events':position,
        'public_commands':calls, 'fits_recomputed':len(fit_records),
        'fit_optimizer_nfev_recomputed':outcome['optimizer_nfev'], 'design_candidates_recomputed':design_candidates,
        'real_physics_and_journal_authenticity_qualified':False, 'complete_population_statistics_audited':False,
        'shared_numerical_helpers':['four/eight marginal estimators', 'nominal D-optimal design', 'controller construction/encoding', 'schema/digest/normalization']}
