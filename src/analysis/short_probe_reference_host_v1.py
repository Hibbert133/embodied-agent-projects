"""Draft evaluator adapter for one cold standard-reference execution.

Reuses the frozen ProbeSession step/noise/ledger implementation without invoking
its capture, restore or warm-history operations. No MetaWorld population is
collected here. The future collector and independent record/statistics audits
are separate obligations, not supplied by this adapter.
"""
from dataclasses import asdict
from time import perf_counter_ns

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.paired_probe_host_v1 import ProbeSession, original_noise
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.operator_identification import encode_controller
from src.probe.short_probe_execution_reference_v1 import METHODS, execute_reference


def execute_short_session(session, method, model, reset_before, *, design=None):
    """Consume one fresh session, preserving actual costs if execution fails.

    reset_before is the collector's ledger snapshot immediately before its one
    controlled initial reset. Audit must also authenticate this outer receipt
    against the event journal; it is never sent to the public actor.
    """
    if type(session) is not ProbeSession or method not in METHODS:
        raise ValueError('registered cold reference and private host session required')
    if (getattr(session, '_short_reference_consumed', False) or session.ctx['calls'] != 0 or
        session.completed or session.attempts or session.captures or session.restores or session._snapshots):
        raise ValueError('unused zero-step session without copies/restores required')
    current_ledger = session.ledger.snapshot()
    if type(reset_before) is not dict or set(reset_before) != {'counts', 'by_phase'}:
        raise ValueError('recorded pre-controlled-reset ledger snapshot required')
    for field in ('reset_attempts', 'reset_completed'):
        before = reset_before['by_phase'].get('CONTROLLED_RESET', {}).get(field, 0)
        after = current_ledger['by_phase'].get('CONTROLLED_RESET', {}).get(field, 0)
        if after-before != 1 or current_ledger['counts'].get(field, 0)-reset_before['counts'].get(field, 0) != 1:
            raise ValueError('exactly one completed controlled initial reset required')
    if current_ledger['counts'].get('reset_errors', 0) != reset_before['counts'].get('reset_errors', 0):
        raise ValueError('failed initial reset cannot authorize execution')
    for field in ('simulation_attempts', 'simulation_completed', 'simulation_frames_attempted', 'simulation_frames_completed'):
        total_delta = current_ledger['counts'].get(field, 0)-reset_before['counts'].get(field, 0)
        reset_delta = (current_ledger['by_phase'].get('CONTROLLED_RESET', {}).get(field, 0)-
                       reset_before['by_phase'].get('CONTROLLED_RESET', {}).get(field, 0))
        if total_delta != reset_delta:
            raise ValueError('extra simulation occurred after the declared initial reset boundary')
    if not session.alive() or not np.array_equal(session.ctx['observation'], session.ctx['initial_observation']):
        raise ValueError('live initial observation boundary required')
    tape = session.ctx['noise_rows']
    if tape.flags.writeable or not np.array_equal(tape, original_noise(session.seed)):
        raise ValueError('unaltered private initial noise tape required')
    budget = session.run_budget
    if (type(budget['completed']) is not int or type(budget['maximum']) is not int or
        budget['completed'] < 0 or budget['maximum']-budget['completed'] < 500):
        raise ValueError('whole-study budget must reserve the complete 500-step case')

    session._short_reference_consumed = True
    session.branch = {'role':'STANDARD_COLD_TASK', 'future':0, 'program':method}
    session._local = 0;session._map = {};session._pending = None
    session.last_rows = [];session.boundaries = {};session.choice_refs = []
    public = {}
    initial_queries = session.policy_queries;initial_completed = budget['completed']
    base = session.env.unwrapped
    addresses = (base.model._address, base.data._address)
    initial_native_time = float(base.data.time)
    started = perf_counter_ns()
    start = session.emit('SHORT_REFERENCE_START', {**session.branch, 'reset_before':reset_before,
        'ledger':current_ledger, 'logical_step':0, **session.witness()})

    def agent_emit(event, payload):
        if event not in ('PROGRAM', 'CHOICE', 'COMMAND', 'FIT_RESULT', 'OUTCOME') or set(payload) & {'sequence', 'saved_ns'}:
            raise ValueError('public event schema or reserved metadata differs')
        if session._pending is not None:
            raise ValueError('previous saved command must execute before another declaration')
        if event == 'PROGRAM':
            if public or session.ctx['calls'] != 0 or payload.get('method') != method or payload.get('task') != session.task or digest(payload.get('initial')) != digest(asdict(session.public())):
                raise ValueError('initial public program differs from actual cold boundary')
        elif not public or type(payload.get('at_calls')) is not int or payload['at_calls'] != session.ctx['calls']:
            raise ValueError('public event must use the current actual clock')
        if event == 'FIT_RESULT':
            prefix = payload['prefix'];count = session.ctx['calls']
            if (count not in (4, 8) or not session.alive() or prefix['task'] != session.task or
                prefix['controlled_reset_completed'] is not True or
                digest(prefix['initial_observation']) != digest(normalize(session.ctx['initial_observation'])) or
                digest(prefix['commands']) != digest(normalize(session.ctx['commands'])) or
                digest(prefix['observations']) != digest(normalize(session.ctx['observations'])) or
                payload['prefix_evidence_sha256'] != digest(prefix)):
                raise ValueError('fitted evidence differs from actual observed probe prefix')
        saved = session._agent_emit(event, payload)
        public[saved['sequence']] = (event, normalize(saved))
        return saved

    def agent_step(saved):
        if session._pending is None or digest(normalize(saved)) != digest(session._pending):
            raise ValueError('only the pending saved command may execute')
        if saved['at_calls'] != session.ctx['calls'] or digest(saved['before']) != digest(asdict(session.public())):
            raise ValueError('saved command has a stale observation or clock')
        reference = public.get(saved['decision_sequence'])
        if reference is None or reference[0] != 'CHOICE':
            raise ValueError('command must reference an earlier public choice')
        choice = reference[1]
        if saved['phase'] == 'FIXED_PROBE':
            if choice['action'] not in ('PROBE_EIGHT', 'PROBE_FOUR', 'COMPLETE_EIGHT', 'COMPLETE_EIGHT_KEEP_FOUR', 'COMPLETE_EIGHT_INVALID_FOUR') or saved['raw_policy'] is not None:
                raise ValueError('probe command lacks its saved probe choice')
            index = session.ctx['calls']-choice['at_calls']
            if not 0 <= index < len(choice['program']):
                raise ValueError('probe command exceeds its saved program')
            expected = np.asarray(choice['program'][index], np.float32)
        elif saved['phase'] == 'POLICY':
            if choice['action'] not in ('RUN_IDENTITY', 'RUN_FITTED') or saved['raw_policy'] is None:
                raise ValueError('policy command lacks its saved controller')
            expected = encode_controller(choice['controller'], saved['raw_policy'])
        else:
            raise ValueError('unregistered command phase')
        if not np.array_equal(expected, np.asarray(saved['command'], np.float32)):
            raise ValueError('sent command differs from saved program or controller')
        return session._agent_step(saved)

    actor = None
    try:
        actor = execute_reference(method, session.task, session.public(), model,
            session.policy_query, agent_step, agent_emit, design=design, remaining_budget=500)
        outcome = actor['outcome'];actual = len(session.last_rows)
        if (outcome['total_steps'] != session.ctx['calls'] or outcome['total_steps'] != actual or
            budget['completed']-initial_completed != actual or
            outcome['policy_queries'] != session.policy_queries-initial_queries or
            outcome['policy_queries'] != sum(row['phase'] == 'POLICY' for row in session.last_rows) or
            outcome['policy_steps'] != sum(row['phase'] == 'POLICY' for row in session.last_rows) or
            outcome['success'] != session.public().success or
            outcome['deadline_loss'] != (actual if session.public().success else 500) or
            outcome['fixed_probe_steps'] != sum(row['phase'] == 'FIXED_PROBE' for row in session.last_rows)):
            raise ValueError('public outcome and actual host execution differ')
        final_ledger = session.ledger.snapshot()
        if (final_ledger['counts'].get('reset_attempts', 0) != current_ledger['counts'].get('reset_attempts', 0) or
            final_ledger['counts'].get('simulation_frames_completed', 0)-current_ledger['counts'].get('simulation_frames_completed', 0) != 5*actual or
            session.captures or session.restores or session._snapshots or
            (base.model._address, base.data._address) != addresses):
            raise ValueError('continuous no-copy lifecycle violated')
        result = {**session.branch, 'start_sequence':start['sequence'], 'outcome':outcome,
            'fit_records':actor['fits'], 'ledger_before':current_ledger, 'ledger_after':final_ledger,
            'policy_query_attempts':session.policy_queries-initial_queries, 'host_command_verifications':actual,
            'wall_ns':perf_counter_ns()-started, 'initial_noise_tape_verifications':1,
            'final_observation':asdict(session.public()), 'end_witness':session.witness(),
            'complete_hidden_state_qualification':False}
        end = session.emit('SHORT_REFERENCE_COMPLETE', result);result['end_sequence'] = end['sequence']
        return normalize(result), actor
    except Exception as error:
        # A callback may fail after simulating frames but before returning its
        # observation. Completed Env.step counts never hide those ledger fees.
        failure = {**session.branch, 'start_sequence':start['sequence'], 'error':type(error).__name__+': '+str(error),
            'step_attempts':session.attempts, 'returned_steps':session.completed,
            'unreturned_step_attempts':session.attempts-session.completed,
            'whole_study_completed_step_delta':budget['completed']-initial_completed,
            'policy_query_attempts':session.policy_queries-initial_queries,
            'ledger_before':current_ledger, 'ledger_after':session.ledger.snapshot(),
            'returned_physical_rows':len(session.last_rows),
            'actor_outcome_available':actor is not None,
            'unvalidated_reported_actor_outcome':None if actor is None else actor['outcome'],
            'completed_fit_results_recorded':sum(event == 'FIT_RESULT' for event, _ in public.values()),
            'known_nfev_in_recorded_fit_results':sum(int(row['fit'].get('nfev', 0)) for event, row in public.values() if event == 'FIT_RESULT'),
            'online_parameter_fits':None, 'optimizer_nfev':None,
            'unavailable_computation_costs_are_unknown_not_zero':True,
            'native_time_before':initial_native_time, 'native_time_after':float(base.data.time),
            'native_transition_completeness_unverified':True}
        try:
            session.emit('SHORT_REFERENCE_ABORTED', failure)
        except Exception:
            pass
        raise
