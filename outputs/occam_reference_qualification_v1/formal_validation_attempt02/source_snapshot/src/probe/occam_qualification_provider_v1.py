"""Frozen-bank own-history reference providers. No private data or capabilities."""
from copy import deepcopy
import math
from src.probe.occam_performance_core_v1 import require,digest,RATES
from src.probe.occam_public_history_v1 import features,state
from src.probe.occam_training_program_v1 import OccamProvider


def check_feedback(declared,measurement,current):
    state(current)
    fields={'schema','start_at','end_at','planned_steps','actual_steps','terminal','success','host_failure',
        'deadline_charge_steps','unexecuted_failure_penalty_steps','potential_before','potential_after','cost','full_window',
        'rows_sha256','terminal_short_label_is_known','no_future_observations_imputed'}
    require(type(measurement) is dict and set(measurement)==fields and measurement.get('schema')=='OCCAM_WINDOW_COST_V1','strict actual window measurement, no private fields')
    n=declared['at_calls'];planned=declared['evaluation_steps'];used=measurement['actual_steps']
    require(type(used) is int and 0<used<=planned and measurement['start_at']==n
        and measurement['end_at']==n+used and measurement['planned_steps']==planned,'consecutive measured window, no future feedback')
    require(type(measurement['full_window']) is bool and measurement['full_window']==(used==planned),'actual full/short flag')
    terminal=any(current[k] for k in ('success','terminated','truncated')) or n+used==500
    require(measurement['terminal']==terminal and measurement['success']==current['success']
        and measurement['host_failure'] is False and (used==planned or terminal),'actual terminal status, no manufactured short window')
    require(type(measurement['cost']) in (float,int) and math.isfinite(measurement['cost']),'finite factual target')
    return terminal


class TrainedProvider:
    """Same fixed beta=0 selector; adaptation is the only mode difference."""
    def __init__(self,bank,*,adapt):
        require(type(adapt) is bool,'explicit adaptation factor')
        self.delegate=OccamProvider(bank,history_steps=8,beta=0.)
        self.adapt=adapt;self.bank_sha256=self.delegate.bank_sha256;self.feedback_windows=0;self.update_attempts=0

    @property
    def session(self):return self.delegate.session

    def declare(self,query):return self.delegate.declare(query)

    def feedback(self,declared,measurement,current):
        session=self.session
        require(session is not None and session.pending is not None and digest(declared)==digest(session.pending),'unchanged pending model declaration')
        terminal=check_feedback(declared,measurement,current)
        before=digest([session.mean,session.cov,session.Q,session.R]);updated=False
        if not measurement['full_window']:
            reason='SUCCESS' if current['success'] else 'TERMINATED' if current['terminated'] else 'TRUNCATED'
            result=session.end_partial(declared,completed_steps=measurement['end_at'],reason=reason)
        elif self.adapt:
            self.update_attempts+=1;require(self.update_attempts<=31,'whole-case filter update budget')
            result=session.complete(declared,completed_steps=measurement['end_at'],observed_performance=[measurement['cost']],executed_rate=declared['selected_rate'])
            updated=True
        else:
            require(session.completed_steps==declared['at_calls'] and session.version==0
                and declared['state_sha256']==before,'frozen model cannot change or skip history')
            session.completed_steps=measurement['end_at'];session.pending=None
            result=dict(status='OBSERVED_WITHOUT_PARAMETER_UPDATE',completed_steps=session.completed_steps,version=0)
        if terminal:session.closed=True
        self.feedback_windows+=1;after=digest([session.mean,session.cov,session.Q,session.R])
        if not updated:require(before==after,'no-update feedback changed model')
        return dict(schema='OCCAM_OWN_HISTORY_FEEDBACK_V1',declaration_sha256=declared['declaration_sha256'],
            completed_steps=measurement['end_at'],adaptation_enabled=self.adapt,update_applied=updated,
            full_window=measurement['full_window'],terminal=terminal,version=session.version,
            model_state_before_sha256=before,model_state_after_sha256=after,result=result)


class FixedRateProvider:
    """All four fixed gains remain controls, with identical receipt accounting."""
    def __init__(self,rate):
        require(type(rate) in (float,int) and rate in RATES,'one of all four registered gains')
        self.rate=float(rate);self.index=RATES.index(rate);self.bank_sha256=digest(dict(schema='FIXED_PI_RATE_V1',rate=self.rate))
        self.pending=None;self.completed=None;self.calls=0;self.closed=False;self.session=None

    def declare(self,query):
        require(not self.closed and self.pending is None and self.calls<31,'live fixed control, one pending window')
        features(query,8);n=query['completed_steps']
        require(self.completed is None or n==self.completed,'actual consecutive fixed-control history')
        d=dict(schema='OCCAM_FIXED_RATE_DECLARATION_V1',at_calls=n,evaluation_steps=query['evaluation_steps'],
            public_query_sha256=digest(query),rates=list(RATES),selected_index=self.index,selected_rate=self.rate,
            fixed_reference_sha256=self.bank_sha256,window_ordinal=self.calls,no_prediction_or_model_update=True)
        d['declaration_sha256']=digest(d);self.pending=deepcopy(d);return deepcopy(d)

    def feedback(self,declared,measurement,current):
        require(self.pending is not None and digest(self.pending)==digest(declared),'unchanged fixed-control declaration')
        terminal=check_feedback(declared,measurement,current);self.completed=measurement['end_at'];self.calls+=1
        self.pending=None;self.closed=terminal
        return dict(schema='OCCAM_FIXED_RATE_FEEDBACK_V1',declaration_sha256=declared['declaration_sha256'],
            completed_steps=self.completed,observed_windows=self.calls,full_window=measurement['full_window'],online_filter_updates=0)
