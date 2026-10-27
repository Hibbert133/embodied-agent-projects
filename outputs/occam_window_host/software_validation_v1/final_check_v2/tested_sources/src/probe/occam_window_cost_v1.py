"""Public, telescoping window cost. Local greedy improvement is not guaranteed.

Terminal short windows have factual labels, without inventing future states.
The original filter contract still skips posterior updates on short windows.
"""
from copy import deepcopy
import numpy as np
from src.probe.occam_public_history_v1 import state,TASKS
from src.probe.occam_performance_core_v1 import require,digest


def ended(current):return any(current[k] for k in ('success','terminated','truncated'))


def potential(task,current,at_calls,*,host_failure=False):
    x=state(current)
    require(task in TASKS and type(at_calls) is int and 0<=at_calls<=500,'registered public potential')
    require(type(host_failure) is bool,'literal failure status')
    if ended(current) or at_calls==500 or host_failure:return 0.
    position=x[:3] if task=='reach-v3' else x[4:7]
    # A fixed one-metre scale, not a fitted estimate of task progress or safety.
    return float(min(1.,np.linalg.norm(position-x[36:39])))


def measure(task,start_at,start,rows,planned_steps,*,host_failure=False):
    require(type(start_at) is int and 0<=start_at<500 and not ended(start),'live segment start')
    state(start)
    require(type(rows) is list and type(planned_steps) is int and 1<=planned_steps<=500-start_at
        and 0<=len(rows)<=planned_steps and type(host_failure) is bool,'actual bounded segment')
    current=deepcopy(start)
    for j,row in enumerate(rows):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==start_at+j
            and row['before']==current and not ended(current),'consecutive factual segment')
        u=np.asarray(row['command'],float)
        require(u.shape==(4,) and np.isfinite(u).all() and max(abs(u))<=1
            and np.array_equal(u,u.astype(np.float32).astype(float)),'actual float32 command')
        state(row['after']);current=row['after']
    stop=start_at+len(rows);terminal=ended(current) or stop==500 or host_failure
    require(len(rows)==planned_steps or terminal,'unexplained short window')
    require(len(rows)>0 or host_failure,'zero physical segment needs explicit host failure')
    charge=(500-start_at) if terminal and not current['success'] else len(rows)
    before=potential(task,start,start_at);after=potential(task,current,stop,host_failure=host_failure)
    return dict(schema='OCCAM_WINDOW_COST_V1',start_at=start_at,end_at=stop,planned_steps=planned_steps,
        actual_steps=len(rows),terminal=terminal,success=current['success'],host_failure=host_failure,
        deadline_charge_steps=charge,unexecuted_failure_penalty_steps=charge-len(rows),
        potential_before=before,potential_after=after,cost=charge/500.+after-before,
        full_window=len(rows)==planned_steps,rows_sha256=digest(rows),
        terminal_short_label_is_known=True,no_future_observations_imputed=True)


def total_cost(task,initial,segments,actual_steps,success):
    require(type(actual_steps) is int and 0<=actual_steps<=500 and type(success) is bool,'actual final status')
    require(type(segments) is list and segments,'nonempty full accounting')
    cursor=0
    for i,s in enumerate(segments):
        require(s['start_at']==cursor and (i==len(segments)-1 or not s['terminal']),'gap/terminal continuation')
        cursor=s['end_at']
    require(cursor==actual_steps and segments[-1]['terminal'],'all paid segments to factual end')
    loss=actual_steps if success else 500
    reconstructed=(sum(s['cost'] for s in segments)+potential(task,initial,0))*500
    require(abs(reconstructed-loss)<1e-9,'telescoping full cutoff loss')
    require(sum(s['deadline_charge_steps'] for s in segments)==loss,'full penalty counted once')
    return dict(deadline_loss=loss,reconstructed_deadline_loss=reconstructed,actual_control_steps=actual_steps,
        actual_steps_not_loss_penalty=True,window_count=len(segments))
