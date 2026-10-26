"""Frozen A1 collector, forecast learning and independent evaluation entry point."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import correction_scope_io_v1 as a


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','collect','audit','train','model-audit','prediction-audit','calibrate','statistics','statistics-audit'))
    p.add_argument('--manifest');p.add_argument('--cohort',choices=a.COHORTS);v=p.parse_args()
    if v.command=='prepare':result=str(a.prepare())
    else:
        p.error('--manifest required') if v.manifest is None else None
        if v.command in ('collect','audit','prediction-audit') and v.cohort is None:p.error('--cohort required')
        if v.command=='collect':
            from src.analysis.correction_scope_collect_v1 import collect
            result=str(collect(v.manifest,v.cohort))
        elif v.command=='audit':
            from src.analysis.correction_scope_audit_v1 import audit
            result=audit(v.manifest,v.cohort)
        elif v.command in ('train','model-audit','prediction-audit','calibrate'):
            from src.analysis import correction_scope_learning_v1 as l
            fn={'train':l.train,'model-audit':l.audit_models,'prediction-audit':l.prediction_audit,'calibrate':l.calibrate}[v.command]
            result=fn(v.manifest,v.cohort) if v.command=='prediction-audit' else fn(v.manifest)
        else:
            from src.analysis import correction_scope_statistics_v1 as s
            result=(s.statistics if v.command=='statistics' else s.audit_statistics)(v.manifest)
    if isinstance(result,dict):result={k:w for k,w in result.items() if k in ('integrity','cohort','executions','control_steps','component_gate','independent_refits','actual_forecast_fits','total_actual_costs')}
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
