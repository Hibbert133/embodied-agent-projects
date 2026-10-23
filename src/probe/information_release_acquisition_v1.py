"""Complete-task-risk acquisition decision; untrained, pure public-data prototype."""
from copy import deepcopy
from src.probe.information_release_v1 import ACTIONS,memory,numeric,ended
from src.probe.information_release_features_v1 import pre_acquisition_features
from src.probe.task_passive_pi_v1 import require,digest

MAX_COST={'CONTINUE':0,'VALIDATE8':8,'MOVE_MEASURE':72}
RESERVED_TAIL=32


def plan(current_memory,completed_history,predicted):
    state=pre_acquisition_features(current_memory,completed_history);m=memory(state['memory'])
    require(not ended(m) and m.completed_steps<500,'actual live pre-acquisition decision')
    require(type(predicted) is dict and set(predicted)==set(ACTIONS),'full registered action population')
    choices=[]
    for i,a in enumerate(ACTIONS):
        r=predicted[a];require(type(r) is dict and set(r)=={'masked_risk','information_effect'},'complete-program risks, no duplicated acquisition charge')
        masked=numeric(r['masked_risk'],0,500);effect=numeric(r['information_effect'])
        numeric(masked+effect,0,500)
        if a=='CONTINUE':require(effect==0,'no supplemental information from an empty trace')
        feasible=a=='CONTINUE' or 500-m.completed_steps>=MAX_COST[a]+RESERVED_TAIL
        if feasible:
            for expose in (False,True) if a!='CONTINUE' else (False,):
                choices.append((masked+(effect if expose else 0.),a!='CONTINUE',expose,i,a))
    score,_,expose,_,a=min(choices)
    return dict(schema='INFORMATION_RELEASE_ACQUISITION_PLAN_V1',before_memory_sha256=m.sha256,
        public_prefix_sha256=digest(state),predicted=deepcopy(predicted),action=a,expose_supplemental_trace=expose,complete_program_risk=score,
        maximum_acquisition_steps=MAX_COST[a],minimum_reserved_tail=RESERVED_TAIL,
        acquisition_cost_already_in_risk=True,physical_safety_guarantee=False,task_benefit_established=False)
