"""Exact constructed scope counterexample; not a robot or SI-OCP replication."""
from fractions import Fraction
from pathlib import Path
from datetime import datetime,timezone
from time import perf_counter_ns
import json
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
ROOT=io.ROOT;BASE=ROOT/'outputs/correction_scope/selective_coverage_v1'
CONFIG=ROOT/'configs/autoresearch/staggered_selective_scope_v1.json'
DELAYS=(1,2,4,8,16);ROUNDS=400;ALPHA=Fraction(1,20)

def encode(q):return [q.numerator,q.denominator]

def generate(delay,out):
    """Threshold learner sees the label only at its registered due time."""
    out=Path(out);out.mkdir(exist_ok=False);threshold=[Fraction(0) for _ in range(delay)];predictions={};counts=dict(predictions=0,labels=0,updates=0,miscovered=0,selected=0,selected_miscovered=0)
    n=delay*ROUNDS;events=0;start=perf_counter_ns()
    with (out/'events.jsonl').open('x',encoding='utf8',newline='\n') as stream:
        def emit(row):
            nonlocal events
            row=dict(event_index=events,**row);stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n');events+=1
        emit(dict(event='INITIAL',delay=delay,rounds_per_thread=ROUNDS,alpha=encode(ALPHA),initial_threshold=encode(Fraction(0)),classification='CONSTRUCTED_SCORE_SEQUENCE_NOT_PHYSICS'))
        for time in range(n+delay):
            if delay<=time<n+delay:
                index=time-delay;thread=index%delay;pred=predictions[index]
                # This deterministic evaluator label is not passed to the selector.
                score=int((index//delay)%20==0)
                emit(dict(event='LABEL',time=time,forecast_index=index,thread=thread,score=score))
                missed=int(Fraction(score)>Fraction(*pred['threshold']))
                before=threshold[thread];io.require(encode(before)==pred['threshold'],'only one pending prediction per calibration thread')
                threshold[thread]=before+missed-ALPHA
                emit(dict(event='THRESHOLD_UPDATE',time=time,forecast_index=index,thread=thread,before=encode(before),miscovered=missed,after=encode(threshold[thread])))
                counts['labels']+=1;counts['updates']+=1;counts['miscovered']+=missed;counts['selected_miscovered']+=pred['selected']*missed
            if time<n:
                thread=time%delay;q=threshold[thread];eligible=time//delay>=20
                # Predictable selection after a complete 20-round warmup per thread.
                row=dict(event='PREDICTION',time=time,forecast_index=time,thread=thread,threshold=encode(q),eligible=eligible,selected=bool(eligible and q==0),label_due=time+delay)
                emit(row);predictions[time]=row;counts['predictions']+=1;counts['selected']+=row['selected']
        emit(dict(event='COMPLETE',time=n+delay,counts=counts,final_thresholds=[encode(q) for q in threshold]))
    io.require(counts==dict(predictions=n,labels=n,updates=n,miscovered=20*delay,selected=19*delay,selected_miscovered=19*delay),'exact closed-form counts')
    result=dict(integrity='FOR_INDEPENDENT_INTEGER_AUDIT',delay=delay,counts=counts,events=events,marginal_coverage=encode(Fraction(n-counts['miscovered'],n)),
        selected_coverage=encode(Fraction(counts['selected']-counts['selected_miscovered'],counts['selected'])),warmup_rounds_per_thread=20,
        first_selected_forecast_time=20*delay,first_selected_label_due=21*delay,first_selected_label_miscovered=True,
        final_thresholds=[encode(q) for q in threshold],events_sha256=io.sha(out/'events.jsonl'),wall_ns=perf_counter_ns()-start)
    io.write(out/'summary.json',result);return result

def prepare(sources):
    frozen=io.read(BASE/'freeze_validation/complete.json');io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean constructed scope freeze')
    io.require(not list(BASE.glob('run_*/manifest.json')),'one constructed scope allocation')
    for n,h in frozen['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged source '+n)
    head=io.git('rev-parse','HEAD');out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol='STAGGERED_SELECTIVE_SCOPE_V1',classification='CONSTRUCTED_SCORE_COUNTEREXAMPLE_NOT_METHOD_OR_ROBOT_QUALIFICATION',source_git_commit=head,
        config=io.read(CONFIG),source_sha256={n:io.sha(ROOT/n) for n in sources});m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'

def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    io.require(path.parent.parent==BASE and mid==io.digest(copy) and m['config']==io.read(CONFIG),'scope manifest ownership')
    for n,h in m['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged constructed scope source')
    return m

def run(path):
    path=Path(path);checked(path);out=path.parent/'construction';out.mkdir(exist_ok=False);guard={};start=perf_counter_ns();summaries=[]
    with read_only(guard):
        for delay in DELAYS:summaries.append(generate(delay,out/('P'+str(delay))))
    io.require(sum(r['counts']['predictions'] for r in summaries)==12400 and sum(r['events'] for r in summaries)==37210,'complete deterministic construction budget')
    result=dict(integrity='FOR_INDEPENDENT_AUDIT',cases=5,forecasts=12400,threshold_updates=12400,events=37210,guard=guard,
        new_physics=0,new_model_fits=0,online_LLM_API_calls=0,random_sampling=0,not_a_SI_OCP_theorem_counterexample=True,wall_ns=perf_counter_ns()-start)
    io.write(out/'receipt.json',result);return result
