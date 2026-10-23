"""Closed research draft; prepare/collection are disabled before any new data."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from datetime import datetime,timezone
import argparse,inspect,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import release_learning_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
io=a.io

PHASES=('prepare','collect','records-audit','receiver-train','receiver-bank-audit','receiver-select','receiver-audit',
    'pre-train','pre-bank-audit','policy-lock','policy-lock-audit','statistics','statistics-audit','pipeline')


def phase(name,path,cohort=None):
    if name=='prepare':return a.prepare()
    m=a.checked(path);root=Path(path).parent
    if name=='collect':
        from src.analysis.release_learning_collect_v1 import collect
        return collect(path,cohort)
    guard={};solves=108 if name=='receiver-train' else 90 if name=='pre-train' else 0
    lstsqs=108 if name=='receiver-bank-audit' else 90 if name=='pre-bank-audit' else 0
    cold=a.limits(cohort)['audit_c4_c8_refits'] if name=='records-audit' else 0
    try:
        with read_only(guard,max_solve=solves,max_lstsq=lstsqs,max_cold_fits=cold):
            if name=='records-audit':
                from src.analysis.release_learning_streaming_audit_v1 import audit
                return audit(path,cohort)
            if name in ('statistics','statistics-audit'):
                from src.analysis import release_learning_statistics_v1 as main
                if name=='statistics':return main.run(path,cohort)
                from src.analysis.release_learning_statistics_audit_v1 import audit
                def deny(*args,**kw):raise RuntimeError('Main statistics and sampling disabled in independent audit')
                with ExitStack() as stack:
                    for key in ('quantile','sampling','compute','run'):stack.enter_context(patch.object(main,key,deny))
                    return audit(path,cohort)
            from src.analysis import release_learning_training_v1 as train
            if name in ('receiver-train','receiver-select','pre-train','policy-lock'):
                return {'receiver-train':train.fit_receiver,'receiver-select':train.select_receiver,'pre-train':train.fit_pre,'policy-lock':train.lock_policy}[name](path)
            from src.analysis import release_learning_model_audit_v1 as independent
            from src.analysis import release_learning_regression_v1 as regression
            from src.probe import release_learning_predictor_v1 as predictor,release_learning_features_v1 as features
            def deny(*args,**kw):raise RuntimeError('Main fitting, features and prediction disabled in independent model audit')
            functions={'receiver-bank-audit':independent.audit_receiver_bank,'receiver-audit':independent.audit_receiver_selection,
                'pre-bank-audit':independent.audit_pre_bank,'policy-lock-audit':independent.audit_policy_lock}
            with ExitStack() as stack:
                for module in (train,predictor,features):
                    for key,fn in inspect.getmembers(module,inspect.isfunction):
                        if fn.__module__==module.__name__:stack.enter_context(patch.object(module,key,deny))
                for key in ('fit','weights'):stack.enter_context(patch.object(regression,key,deny))
                return functions[name](path)
    except BaseException:
        failure=root/'process_failures';failure.mkdir(exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        io.write(failure/(name+'_'+str(cohort)+'_'+stamp+'.json'),dict(phase=name,cohort=cohort,traceback=traceback.format_exc()));raise
    finally:
        folder=root/cohort.lower() if cohort is not None else root/'models'
        if folder.exists():io.write(folder/(name.replace('-','_')+'_guard.json'),guard)


def pipeline(path):
    if path is None:path=a.prepare()
    def go(name,cohort=None):
        print(dict(phase=name,cohort=cohort,status='STARTING'),flush=True);value=phase(name,path,cohort)
        print(dict(phase=name,cohort=cohort,status='COMPLETED'),flush=True);return value
    go('collect','SOFTWARE_NATIVE');go('records-audit','SOFTWARE_NATIVE')
    go('collect','TAIL_TRAIN');go('records-audit','TAIL_TRAIN');go('receiver-train');go('receiver-bank-audit')
    go('collect','TAIL_SELECT');go('records-audit','TAIL_SELECT');go('receiver-select');go('receiver-audit')
    go('collect','GATE_TRAIN');go('records-audit','GATE_TRAIN');go('pre-train');go('pre-bank-audit')
    go('collect','CAL');go('records-audit','CAL');go('policy-lock');go('policy-lock-audit')
    go('collect','DEV');go('records-audit','DEV');go('statistics','DEV');r=go('statistics-audit','DEV')
    if r['DEV_gate']!='PASSED':
        io.write(Path(path).parent/'development_stop.json',dict(status='NEGATIVE_DEVELOPMENT_CLOSED_VERSION',DEV_gate=r['DEV_gate'],
            no_QUAL_collected=True,no_extension_or_tuning=True,publication_goal_complete=False));return path
    go('collect','QUAL');go('records-audit','QUAL');go('statistics','QUAL');go('statistics-audit','QUAL');return path


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=PHASES);p.add_argument('--manifest',type=Path);p.add_argument('--cohort',choices=a.COHORTS);v=p.parse_args()
    if v.phase=='pipeline':print(pipeline(v.manifest),flush=True)
    else:
        if v.phase!='prepare':io.require(v.manifest is not None,'frozen manifest required')
        if v.phase in ('collect','records-audit','statistics','statistics-audit'):io.require(v.cohort is not None,'registered cohort required')
        r=phase(v.phase,v.manifest,v.cohort);print(r if isinstance(r,(str,Path)) else {k:r[k] for k in ('integrity','DEV_gate','QUAL_gate','fits','grid_index') if k in r},flush=True)
