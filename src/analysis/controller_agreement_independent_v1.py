"""Literal scalar PI and actual paired-journal checks; no main replay imports."""
import numpy as np


def demand(ok, message):
    if not ok:
        raise ValueError(message)


def command(raw, integral, task, rate):
    demand(task in ('push-v3', 'reach-v3', 'door-open-v3') and rate in (.125, .5, 2., 8.), 'known public controller')
    demand(len(raw) == 4 and len(integral) == 2 and np.isfinite(list(raw)+list(integral)).all(), 'finite public numbers')
    demand(all(float(np.float32(x)) == x for x in raw), 'saved float32 policy output')
    gain = {'push-v3':10., 'reach-v3':5., 'door-open-v3':25.}[task]
    base = [float(np.float32(min(1., max(-1., x)))) for x in raw]
    sent = list(base)
    for axis in (0, 1):
        proposed = integral[axis] + .0125*(gain*(raw[axis]/gain)/rate)
        bounded = min(2., max(-2., proposed))
        sent[axis] = float(np.float32(min(1., max(-1., base[axis]+bounded))))
    return sent, [sent[i]-base[i] for i in (0, 1)]


def reconstruct(entry, rows, receiver_rate):
    integral = list(entry['integral_xy']); step = entry['completed_steps']; current = entry['current']; trace = []
    demand(entry['controller'] == dict(source='UNCORRECTED', matrix_xy=[[1.,0.],[0.,1.]], offset=[0.,0.,0.,0.]), 'identity base')
    for row in rows:
        demand(row['at_calls'] == step and row['before'] == current, 'literal prefix continuity')
        demand(step < 500 and not any(current[k] for k in ('success','terminated','truncated')), 'live prefix')
        sent, after = command(row['raw_policy'], integral, entry['task'], receiver_rate)
        matched = sent == row['command']
        trace.append(dict(at_calls=step, raw_policy=list(row['raw_policy']), integral_before=integral,
            proposed_command=sent, factual_command=list(row['command']), matches=matched, integral_after_receipt=after if matched else None))
        if not matched:
            return dict(status='FIRST_DISAGREEMENT', matched_steps=len(trace)-1, first_disagreement_at_calls=step, trace=trace)
        integral = after; current = row['after']; step += 1
    terminal = step == 500 or any(current[k] for k in ('success','terminated','truncated'))
    return dict(status='MATCHED_TO_TERMINAL' if terminal else 'RIGHT_CENSORED_RECORD', matched_steps=len(trace), first_disagreement_at_calls=None, trace=trace)


def paired_check(source, target, prediction):
    """Target outcomes only validate the descriptive replay, never feed it."""
    a, b = source['entry'], target['entry']
    demand((a is None) == (b is None), 'paired entry availability differs')
    if a is None:
        demand(source['outcome'] == target['outcome'], 'pre-adoption outcome differs')
        return dict(paired_common_receipts=0, no_adoption_outcome_equal=True)
    demand({k:v for k,v in a.items() if k != 'time_constant_s'} == {k:v for k,v in b.items() if k != 'time_constant_s'}, 'common acquisition return differs')
    demand(source['entry_witness'] == target['entry_witness'], 'saved native/noise-cursor return witness differs')
    left, right = source['rows'], target['rows']; common = prediction['matched_steps']
    demand(len(right) >= common, 'paired target ended before matched prefix')
    for i in range(common):
        demand(left[i] == right[i], 'actual paired public prefix differs before disagreement')
    if prediction['status'] == 'FIRST_DISAGREEMENT':
        demand(len(right) > common and len(left) > common, 'missing actual divergent command')
        x, y = left[common], right[common]
        demand(x['before'] == y['before'] and x['raw_policy'] == y['raw_policy'], 'different information before divergent command')
        demand(x['command'] != y['command'] and prediction['trace'][-1]['proposed_command'] == y['command'], 'literal first disagreement does not match actual other arm')
    if prediction['status'] == 'MATCHED_TO_TERMINAL':
        demand(len(left) == len(right) == common and source['outcome'] == target['outcome'], 'terminal certificate contradicted by paired actual execution')
    lower = upper = 0
    if prediction['status'] != 'MATCHED_TO_TERMINAL':
        lower = a['completed_steps'] + common + 1 - source['outcome']['deadline_loss']
        upper = 500 - source['outcome']['deadline_loss']
    delta = target['outcome']['deadline_loss'] - source['outcome']['deadline_loss']
    demand(lower <= delta <= upper, 'actual task delta outside causal prefix bound')
    return dict(paired_common_receipts=common, actual_loss_delta=delta, independently_rebuilt_interval=[lower, upper],
        actual_success_to_failure=bool(source['outcome']['success'] and not target['outcome']['success']),
        actual_failure_to_success=bool(not source['outcome']['success'] and target['outcome']['success']))
