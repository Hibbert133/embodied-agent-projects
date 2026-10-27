"""Preassigned TRAIN behavior; no reward fitting, latent parameters or online RNG.

The evaluator commits a separately randomized legal schedule before collection.
The feature/model schema never receives its registry seed or true fault.
"""
from copy import deepcopy
from src.probe.occam_performance_core_v1 import require,digest,RATES
from src.probe.occam_public_history_v1 import features


class BehaviorProvider:
    def __init__(self,schedule):
        require(type(schedule) in (list,tuple) and len(schedule)==31 and all(type(i) is int and 0<=i<4 for i in schedule),'committed legal 31-window schedule')
        self.schedule=tuple(schedule);self.bank_sha256=digest(dict(schema='ASSIGNED_TRAIN_SCHEDULE_V1',schedule=schedule))
        self.pending=None;self.completed=None;self.calls=0;self.closed=False;self.session=None

    def declare(self,query):
        require(not self.closed and self.pending is None and self.calls<len(self.schedule),'live schedule without pending feedback')
        features(query,8);n=query['completed_steps']
        require(self.completed is None or self.completed==n,'consecutive actual training windows')
        index=self.schedule[self.calls]
        d=dict(schema='OCCAM_TRAIN_BEHAVIOR_DECLARATION_V1',at_calls=n,evaluation_steps=query['evaluation_steps'],
            public_query_sha256=digest(query),rates=list(RATES),selected_index=index,selected_rate=RATES[index],
            assignment_ordinal=self.calls,schedule_sha256=self.bank_sha256,no_prediction_or_model_update=True)
        d['declaration_sha256']=digest(d);self.pending=deepcopy(d);return deepcopy(d)

    def feedback(self,declared,measurement,current):
        require(self.pending is not None and digest(declared)==digest(self.pending),'unchanged saved behavior decision')
        d=self.pending;used=measurement['actual_steps'];require(measurement['start_at']==d['at_calls']
            and measurement['end_at']==d['at_calls']+used and 0<used<=d['evaluation_steps']
            and measurement['full_window']==(used==d['evaluation_steps']),'actual training feedback length')
        terminal=any(current[k] for k in ('success','terminated','truncated')) or measurement['end_at']==500
        require(measurement['terminal']==terminal and (used==d['evaluation_steps'] or terminal),'no invented live short feedback')
        self.completed=measurement['end_at'];self.calls+=1;self.closed=terminal;self.pending=None
        return dict(schema='OCCAM_TRAIN_BEHAVIOR_FEEDBACK_V1',declaration_sha256=d['declaration_sha256'],completed_steps=self.completed,
            recorded_windows=self.calls,complete_window=measurement['full_window'],online_filter_updates=0,training_or_fit_performed=False)
