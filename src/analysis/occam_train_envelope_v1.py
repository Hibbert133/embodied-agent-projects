"""Independent allocation/identity/closure/clock envelope checks, no actor import."""
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.response_qualification_io_v1 import digest,require

IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
KEYS=('phase','group','task','seed','context','planned_boundary','acquisition_action','behavior')


def bind_case(manifest,spec,case,events,private,previous):
    require(type(previous) is tuple and len(previous)==4,'sequence and clock cursors')
    es,ps,et,pt=previous
    for k in IDENTITY:require(case[k]==manifest[k],'case manifest identity '+k)
    require({k:case[k] for k in KEYS}==spec,'complete allocation spec')
    require(events and events[0]['event']=='CASE_ALLOCATION' and events[-1]['event']=='CASE_COMPLETE','complete event bracket')
    require(case['event_start_sequence']==events[0]['sequence']==es
        and case['event_end_sequence_exclusive']==events[-1]['sequence'],'case exclusive closure')
    require(events[-1]['case_record_sha256']==digest(normalize(case)),'case bytes differ from closure')
    require(events[-1]['total_steps']==case['total_steps'] and events[-1]['deadline_loss']==case['deadline_loss'],'case summary differs')
    for stream,cursor,stamp in ((events,es,et),(private,ps,pt)):
        for row in stream:
            require(row['sequence']==cursor and row['saved_ns']>stamp,'global stream cursor/clock reversed')
            require({k:row[k] for k in KEYS}==spec,'cross-case event ownership')
            for k in IDENTITY:require(row[k]==manifest[k],'event manifest identity '+k)
            cursor+=1;stamp=row['saved_ns']
        if stream is events:es,et=cursor,stamp
        else:ps,pt=cursor,stamp
    return es,ps,et,pt
