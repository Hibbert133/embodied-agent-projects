"""Independent cold-reference journal replay, without actor or Env execution.

The public-program parser and numerical inference/design/encoding are shared.
This layer reconstructs saved-command consumption, fixed-policy outputs, private
input noise, lifecycle charges and physical clock continuity. Native signatures
are source-generated witnesses; this is not independent physics or a universal
hidden-state proof. Population allocation/statistics remain separate obligations.
"""
from copy import deepcopy
import math

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_public_audit_v1 import audit_public_run, METHODS, same
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.forward_prediction import vector
from src.rollout.task_registry import create_task_policy


BRANCH = {'role':'STANDARD_COLD_TASK', 'future':0}
PHYSICAL = ('logical_step', 'phase', 'command', 'raw_policy', 'executed_action_oracle',
            'after', 'reward', 'info', 'simulation_time_before', 'simulation_time_after', 'noise_cursor_after')
WITNESS = ('native_sha256', 'python_semantic_sha256', 'noise_past_sha256', 'simulation_time')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ledger_add(value, phase, field, count):
    result = deepcopy(value)
    for cell in (result['counts'], result['by_phase'].setdefault(phase, {})):
        cell[field] = cell.get(field, 0)+count
    return result


def simulation(value, phase, calls, frames):
    for field, count in (('simulation_attempts', calls), ('simulation_completed', calls),
                         ('simulation_frames_attempted', frames), ('simulation_frames_completed', frames)):
        value = ledger_add(value, phase, field, count)
    return value


def check_ledger(value):
    require(type(value) is dict and set(value) == {'counts', 'by_phase'}, 'strict lifecycle ledger required')
    require(type(value['counts']) is dict and type(value['by_phase']) is dict, 'invalid ledger cells')
    phases = ('FACTORY_SETUP', 'GOAL_GENERATION', 'CONTROLLED_RESET', 'CONTROL')
    total = {}
    for phase, fields in value['by_phase'].items():
        require(phase in phases and type(fields) is dict, 'unregistered lifecycle phase')
        for name, count in fields.items():
            require(type(name) is str and type(count) is int and count >= 0, 'invalid lifecycle charge')
            total[name] = total.get(name, 0)+count
    same(value['counts'], total)
    require(not any(value['counts'].get(key, 0) for key in ('reset_errors', 'simulation_errors',
        'uncertain_simulation_frames', 'frame_budget_rejections')), 'failed lifecycle cannot enter completed cohort')


def check_observation(value):
    require(type(value) is dict and set(value) == {'observation', 'success', 'terminated', 'truncated'},
            'strict observed state required')
    vector(value['observation'], 39)
    require(all(type(value[key]) is bool for key in ('success', 'terminated', 'truncated')), 'boolean ending flags required')


def noise_tape(seed):
    key = int(np.random.SeedSequence([seed, 47001]).generate_state(1)[0])
    return np.random.default_rng(key).normal(0, .05, (500, 3)).astype('<f4')


def applied(command, fault, noise):
    result = np.asarray(command, np.float32).copy()
    latent = np.asarray(fault['matrix_xy'], np.float32)@result[:2]+np.asarray(fault['bias_xy'], np.float32)
    zone = np.asarray(fault['deadzone_xy'], np.float32)
    result[:2] = np.sign(latent)*np.maximum(np.abs(latent)-zone, np.float32(0))/(np.float32(1)-zone)
    result[:3] += noise
    return np.clip(result, -1, 1).tolist()


def physical_rows_equal(left, right, count):
    """Compare only the registered same-prefix fields; omit wall-clock timer info."""
    require(type(count) is int and count >= 0, 'nonnegative completed prefix required')
    if len(left) < count or len(right) < count:
        return False
    def selected(row):
        value = deepcopy({key:row[key] for key in PHYSICAL})
        if type(value['info'].get('episode')) is dict:
            value['info']['episode'].pop('t', None)
        return value
    return all(digest(selected(a)) == digest(selected(b)) for a, b in zip(left[:count], right[:count]))


def audit_journal(events, public_record, host_record, spec, model, *, design=None,
                  initial_ledger=None, identity=None, previous_sequence=-1, previous_saved_ns=-1):
    """Replay exactly one complete factory, initial reset and cold execution.

    spec contains evaluator-only task/seed/method/fault; it is never an actor
    input. identity and prior journal clock must come from the population reader.
    No custom policy can be supplied; the registered fixed task policy is queried.
    """
    require(type(spec) is dict and set(spec) == {'task', 'seed', 'method', 'fault_oracle'}, 'strict evaluator allocation required')
    require(spec['method'] in METHODS and type(spec['seed']) is int and spec['seed'] >= 0, 'registered method and task seed required')
    fault = spec['fault_oracle']
    require(type(fault) is dict and set(fault) == {'matrix_xy', 'bias_xy', 'deadzone_xy'}, 'registered private fault required')
    for field, shape in (('matrix_xy', (2, 2)), ('bias_xy', (2,)), ('deadzone_xy', (2,))):
        value = np.asarray(fault[field], float)
        require(value.shape == shape and np.isfinite(value).all(), 'finite private actuator coefficients required')
    require(np.all(np.asarray(fault['deadzone_xy']) >= 0) and np.all(np.asarray(fault['deadzone_xy']) < 1), 'private deadzone outside domain')
    require(type(events) is list and events and type(public_record) is dict and type(host_record) is dict, 'complete records required')
    same(public_record['method'], spec['method'])
    identity = {} if identity is None else deepcopy(identity)
    require(type(identity) is dict and set(identity) <= {'experiment_run_id', 'manifest_id', 'source_git_commit',
        'study_phase', 'stream', 'episode', 'task', 'seed', 'method'}, 'reserved or unknown journal identity field')
    for key in ('task', 'seed', 'method'):
        if key in identity:
            same(identity[key], spec[key])
    ledger = deepcopy({'counts':{}, 'by_phase':{}} if initial_ledger is None else initial_ledger)
    check_ledger(ledger)
    require(type(previous_sequence) is int and previous_sequence >= -1 and type(previous_saved_ns) is int and previous_saved_ns >= -1,
            'strict previous global journal position required')
    tape = noise_tape(spec['seed']);policy = create_task_policy(spec['task'])
    branch = {**BRANCH, 'program':spec['method']}
    prior_sequence = previous_sequence;prior_time = previous_saved_ns
    factory = 0;factory_resets = 0;controlled = 0;reset = None;reset_before = None
    initial = None;current = None;clock = None;start = None;complete = None
    public_events = [];trace = [];physical = [];command = None;intent = None
    steps = 0;queries = 0;boundary_due = False;boundaries = {};latest_witness = None

    def live():
        return current is not None and not any(current[key] for key in ('success', 'terminated', 'truncated'))

    def body(event, fields, branched=False):
        want = set(identity) | {'event', 'sequence', 'saved_ns'} | set(fields)
        if branched:
            want |= set(branch)
            for key, value in branch.items():
                same(event[key], value)
        require(set(event) == want, 'unknown or missing outer event field: '+event['event'])

    def witness(event):
        same(event['simulation_time'], clock)
        same(event['noise_past_sha256'], digest(tape[:steps].tolist()))
        for key in ('native_sha256', 'python_semantic_sha256'):
            value = event[key]
            require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'invalid source state witness')
        return {key:deepcopy(event[key]) for key in WITNESS}

    for event in events:
        normalize(event)
        require(type(event) is dict and type(event.get('sequence')) is int and event['sequence'] == prior_sequence+1,
                'global journal sequence gap or duplication')
        require(type(event.get('saved_ns')) is int and event['saved_ns'] >= 0 and event['saved_ns'] >= prior_time, 'journal wall clock reversal')
        for key, value in identity.items():
            same(event[key], value)
        prior_sequence = event['sequence'];prior_time = event['saved_ns'];kind = event['event']
        require(complete is None, 'event after completed execution')
        require(not boundary_due or kind == 'PHYSICAL_BOUNDARY', 'missing immediate four/eight-step boundary')
        if kind == 'FACTORY_INTENT':
            body(event, ('ledger',));require(factory == 0 and initial is None and reset is None, 'duplicate factory')
            same(event['ledger'], ledger);factory = 1
        elif kind == 'LIFECYCLE_RESET_INTENT':
            body(event, ('phase', 'before'))
            require(reset is None and initial is None, 'nested reset or reset during task')
            phase = event['phase']
            require((factory == 1 and phase == 'GOAL_GENERATION' and factory_resets < 50) or
                    (factory == 2 and phase == 'CONTROLLED_RESET' and controlled == 0), 'unregistered initial reset allocation')
            same(event['before'], ledger);reset = event
            if phase == 'CONTROLLED_RESET':
                reset_before = deepcopy(ledger)
            ledger = ledger_add(ledger, phase, 'reset_attempts', 1)
        elif kind == 'LIFECYCLE_RESET_COMPLETE':
            body(event, ('intent_sequence', 'phase', 'after'))
            require(reset is not None and event['intent_sequence'] == reset['sequence'] and event['phase'] == reset['phase'], 'orphan reset completion')
            ledger = simulation(ledger, event['phase'], 100, 500)
            ledger = ledger_add(ledger, event['phase'], 'reset_completed', 1)
            same(event['after'], ledger)
            factory_resets += int(event['phase'] == 'GOAL_GENERATION');controlled += int(event['phase'] == 'CONTROLLED_RESET');reset = None
        elif kind == 'FACTORY_COMPLETE':
            body(event, ('ledger',));require(factory == 1 and reset is None and factory_resets == 50, 'incomplete factory lifecycle')
            same(event['ledger'], ledger);factory = 2
        elif kind == 'CONTROLLED_INITIAL':
            body(event, ('task', 'observation', 'simulation_time', 'ledger'))
            require(factory == 2 and controlled == 1 and initial is None and reset is None, 'one completed initial reset required')
            same(event['task'], spec['task']);same(event['ledger'], ledger)
            vector(event['observation'], 39)
            require(type(event['simulation_time']) is float and math.isfinite(event['simulation_time']), 'finite initial simulation clock required')
            initial = deepcopy(event['observation']);current = {'observation':initial, 'success':False, 'terminated':False, 'truncated':False};clock = event['simulation_time']
        elif kind == 'SHORT_REFERENCE_START':
            body(event, ('reset_before', 'ledger', 'logical_step', *WITNESS), True)
            require(start is None and live() and steps == event['logical_step'] == 0, 'nonzero/reused execution boundary')
            same(event['reset_before'], reset_before);same(event['ledger'], ledger);latest_witness = witness(event);start = event
        elif kind == 'AGENT_EVENT':
            body(event, ('agent_event', 'public_payload'), True)
            require(start is not None and command is None and intent is None, 'public declaration outside idle execution')
            p = event['public_payload']
            require(type(p) is dict and type(p.get('saved_ns')) is int and start['saved_ns'] <= p['saved_ns'] <= event['saved_ns'], 'public declaration not saved at claimed time')
            public_events.append({'event':event['agent_event'], 'public_payload':deepcopy(p)})
            if event['agent_event'] == 'COMMAND':
                require(live() and steps < 500 and p['at_calls'] == steps, 'command after ending or wrong current clock')
                same(p['before'], current);vector(p['command'], 4)
                require(np.all(np.abs(p['command']) <= 1), 'unbounded saved command')
                if p['phase'] == 'POLICY':
                    expected = np.asarray(policy.get_action(np.asarray(current['observation']).copy()), np.float32).tolist()
                    same(p['raw_policy'], expected);queries += 1
                else:
                    require(p['phase'] == 'FIXED_PROBE' and p['raw_policy'] is None, 'unknown physical command phase')
                command = event
        elif kind == 'STEP_INTENT':
            body(event, ('logical_step', 'global_command_sequence', 'phase', 'command', 'ledger_before'), True)
            require(command is not None and intent is None and event['logical_step'] == steps and live(), 'step lacks pending saved command')
            same(event['global_command_sequence'], command['sequence']);same(event['phase'], command['public_payload']['phase'])
            same(event['command'], command['public_payload']['command']);same(event['ledger_before'], ledger);intent = event
        elif kind == 'STEP_COMPLETE':
            body(event, (*PHYSICAL, 'intent_sequence', 'global_command_sequence', 'execution_started_ns', 'completed_ns', 'ledger_before', 'ledger_after'), True)
            require(intent is not None and command is not None and event['logical_step'] == steps, 'step completion lacks matching intent')
            same(event['intent_sequence'], intent['sequence']);same(event['global_command_sequence'], command['sequence'])
            same(event['command'], intent['command']);same(event['phase'], intent['phase']);same(event['raw_policy'], command['public_payload']['raw_policy'])
            require(type(event['execution_started_ns']) is int and type(event['completed_ns']) is int and
                    command['saved_ns'] <= intent['saved_ns'] <= event['execution_started_ns'] <= event['completed_ns'] <= event['saved_ns'], 'saved decision must precede execution and result')
            same(event['simulation_time_before'], clock)
            require(type(event['simulation_time_after']) is float and math.isfinite(event['simulation_time_after']) and
                    np.isclose(event['simulation_time_after']-clock, .0125, atol=1e-10, rtol=0), 'continuous five-frame physical clock violated')
            same(event['ledger_before'], ledger);ledger = simulation(ledger, 'CONTROL', 1, 5);same(event['ledger_after'], ledger)
            same(event['executed_action_oracle'], applied(event['command'], fault, tape[steps]))
            check_observation(event['after']);require(type(event['info']) is dict, 'physical info must be an object')
            same(event['after']['success'], bool(event['info'].get('success', False)))
            require(type(event['reward']) in (int, float) and math.isfinite(event['reward']), 'finite physical reward required')
            row = {'logical_step':steps, 'phase':event['phase'], 'command':event['command'], 'raw_policy':event['raw_policy'],
                'command_sequence':command['public_payload']['sequence'], 'decision_sequence':command['public_payload']['decision_sequence'],
                'before':deepcopy(current), 'after':deepcopy(event['after'])}
            trace.append(row);physical.append({key:deepcopy(event[key]) for key in PHYSICAL})
            steps += 1;same(event['noise_cursor_after'], steps);clock = event['simulation_time_after'];current = deepcopy(event['after'])
            boundary_due = steps in (4, 8);intent = command = None;latest_witness = None
        elif kind == 'PHYSICAL_BOUNDARY':
            body(event, ('logical_step', *WITNESS), True)
            require(boundary_due and event['logical_step'] == steps and steps not in boundaries, 'unscheduled/duplicate physical boundary')
            latest_witness = witness(event);boundaries[steps] = deepcopy(latest_witness);boundary_due = False
        elif kind == 'SHORT_REFERENCE_COMPLETE':
            fields = ('start_sequence', 'outcome', 'fit_records', 'ledger_before', 'ledger_after', 'policy_query_attempts',
                'host_command_verifications', 'wall_ns', 'initial_noise_tape_verifications', 'final_observation', 'end_witness', 'complete_hidden_state_qualification')
            body(event, fields, True)
            require(start is not None and command is None and intent is None, 'incomplete execution')
            same(event['start_sequence'], start['sequence']);same(event['ledger_before'], start['ledger']);same(event['ledger_after'], ledger)
            same(event['outcome'], public_record['outcome']);same(event['fit_records'], public_record['fits'])
            same(event['policy_query_attempts'], queries);same(event['host_command_verifications'], steps)
            same(event['initial_noise_tape_verifications'], 1);same(event['complete_hidden_state_qualification'], False)
            require(type(event['wall_ns']) is int and event['wall_ns'] >= 0, 'nonnegative recorded host duration required')
            same(event['final_observation'], current);end_witness = witness(event['end_witness'])
            if latest_witness is not None:
                same(end_witness, latest_witness)
            expected_host = {key:deepcopy(event[key]) for key in (*branch, *fields)}
            expected_host['end_sequence'] = event['sequence'];same(host_record, expected_host);complete = event
        else:
            raise ValueError('unregistered physical event: '+str(kind))
    require(complete is not None and not boundary_due and reset is None, 'unfinished factory/reset/task journal')
    same(public_record['events'], public_events);same(public_record['trace'], trace)
    public_audit = audit_public_run(public_record, spec['task'], model, design=design)
    check_ledger(ledger)
    return {'integrity':'COLD_JOURNAL_CONSISTENT', 'method':spec['method'], 'events_checked':len(events),
        'last_sequence':prior_sequence, 'last_saved_ns':prior_time, 'ledger':ledger, 'controlled_steps':steps,
        'controlled_resets':controlled, 'factory_resets':factory_resets, 'policy_queries_recomputed':queries,
        'public_audit':public_audit, 'physical_rows':physical, 'initial_observation':initial,
        'start_witness':{key:start[key] for key in WITNESS}, 'boundaries':boundaries,
        'independent_physics_execution':False, 'universal_complete_hidden_state_qualification':False,
        'complete_population_statistics_audited':False}


def audit_matched_unit(runs):
    """Check the registered initial witnesses and actually completed probe pairs.

    Caller must supply seven successful audit_journal returns for the same
    allocated seed/task/fault. This does not authenticate population ownership.
    Cross-method Python signatures are retained but not asserted identical;
    initial observation, native signature and simulation time are registered.
    """
    require(type(runs) is dict and set(runs) == set(METHODS), 'all seven audited methods required')
    anchor = runs['NO_PROBE']
    for method, value in runs.items():
        require(value['integrity'] == 'COLD_JOURNAL_CONSISTENT' and value['method'] == method,
                'complete method journal required before prefix matching')
        same(value['initial_observation'], anchor['initial_observation'])
        for key in ('native_sha256', 'simulation_time'):
            same(value['start_witness'][key], anchor['start_witness'][key])
    pairs = []
    def compare(left, right, count):
        a = runs[left]['physical_rows'];b = runs[right]['physical_rows'];observed = min(count, len(a), len(b))
        require(physical_rows_equal(a, b, observed), 'actual common probe prefix differs')
        pairs.append({'methods':[left, right], 'required_prefix_steps':count, 'observed_common_steps':observed,
            'complete':observed == count,
            'incomplete_reason':None if observed == count else 'TASK_ENDED_BEFORE_COMPLETE_PREFIX'})
    for other in ('DOPT4_UPDATE', 'DOPT4_KEEP_AT8', 'DOPT4_FALLBACK8'):
        compare('DOPT8_UPDATE', other, 4)
    compare('DOPT8_UPDATE', 'DOPT4_KEEP_AT8', 8)
    fallback = runs['DOPT4_FALLBACK8']['physical_rows']
    fallback_extension_observed = len(fallback) > 4 and fallback[4]['phase'] == 'FIXED_PROBE'
    if fallback_extension_observed:
        compare('DOPT8_UPDATE', 'DOPT4_FALLBACK8', 8)
    return {'integrity':'REGISTERED_PREFIXES_CONSISTENT', 'initial_native_and_observation_matches':6,
        'pairs':pairs, 'fallback_probe_extension_observed':fallback_extension_observed,
        'complete_prefix_pairs':sum(row['complete'] for row in pairs),
        'incomplete_prefix_pairs':sum(not row['complete'] for row in pairs),
        'universal_complete_hidden_state_qualification':False, 'population_ownership_authenticated':False}
