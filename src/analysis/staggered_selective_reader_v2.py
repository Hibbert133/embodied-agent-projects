"""Integer 1/20 units and literal chronology, independent of Fraction learner."""
from pathlib import Path
from math import gcd
import json
from time import perf_counter_ns
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only

def plain_rows(path):
    with Path(path).open('r',encoding='utf8') as stream:
        for line in stream:yield json.loads(line)

def rational(units):
    divisor=gcd(units,20);return [units//divisor,20//divisor]

def audit(path):
    path=Path(path);out=path.parent/'construction';start=perf_counter_ns();guard={};total_events=0;totals=0;updates=0;checks=[]
    with read_only(guard):
        for p in (1,2,4,8,16):
            folder=out/('P'+str(p));summary=io.read(folder/'summary.json');io.require(io.sha(folder/'events.jsonl')==summary['events_sha256'],'complete source events')
            iterator=iter(plain_rows(folder/'events.jsonl'));event_index=0;states=[0]*p;selected={};counts=dict(predictions=0,labels=0,updates=0,miscovered=0,selected=0,selected_miscovered=0)
            def consume(expected):
                nonlocal event_index
                actual=next(iterator);io.require(actual==dict(event_index=event_index,**expected),'literal independent event, fields and causal order');event_index+=1
            consume(dict(event='INITIAL',delay=p,rounds_per_thread=400,alpha=[1,20],initial_threshold=[0,1],classification='CONSTRUCTED_SCORE_SEQUENCE_NOT_PHYSICS'))
            for time in range(401*p):
                if time>=p:
                    index=time-p;thread=index%p;score=1 if (index//p)%20==0 else 0;before=states[thread];missed=int(20*score>before)
                    consume(dict(event='LABEL',time=time,forecast_index=index,thread=thread,score=score))
                    states[thread]+=20*missed-1
                    consume(dict(event='THRESHOLD_UPDATE',time=time,forecast_index=index,thread=thread,before=rational(before),miscovered=missed,after=rational(states[thread])))
                    counts['labels']+=1;counts['updates']+=1;counts['miscovered']+=missed;counts['selected_miscovered']+=selected[index]*missed;updates+=1
                if time<400*p:
                    thread=time%p;eligible=time//p>=20;choose=bool(eligible and states[thread]==0);selected[time]=choose
                    consume(dict(event='PREDICTION',time=time,forecast_index=time,thread=thread,threshold=rational(states[thread]),eligible=eligible,selected=choose,label_due=time+p))
                    counts['predictions']+=1;counts['selected']+=choose
            consume(dict(event='COMPLETE',time=401*p,counts=counts,final_thresholds=[rational(v) for v in states]));io.require(next(iterator,None) is None,'no extra evidence events')
            io.require(counts==dict(predictions=400*p,labels=400*p,updates=400*p,miscovered=20*p,selected=19*p,selected_miscovered=19*p),'independent formula for every case')
            io.require(summary['counts']==counts and summary['events']==event_index and summary['marginal_coverage']==[19,20] and summary['selected_coverage']==[0,1],'exact all-forecast and selected-forecast coverage')
            io.require(all(v==0 for v in states) and summary['final_thresholds']==[[0,1]]*p,'telescoping calibration accounting')
            checks.append(dict(delay=p,forecasts=400*p,threshold_updates=400*p,selected=19*p,marginal_coverage=[19,20],selected_coverage=[0,1],all_labels_after_prediction=True))
            total_events+=event_index;totals+=400*p
    io.require((total_events,totals,updates)==(37210,12400,12400),'all exact-case costs')
    result=dict(integrity='PASSED',cases=checks,events=total_events,forecasts=totals,independent_integer_reconstruction_updates=updates,
        main_Fraction_generator_not_called=True,chronology_and_strict_field_checks=True,guard=guard,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
        not_a_new_algorithm_or_SI_OCP_replication=True,wall_ns=perf_counter_ns()-start)
    io.write(path.parent/'reader_audit_v2/audit.json',result);return result
