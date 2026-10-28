"""Reconstruct all prefix-analysis arithmetic counts from checked result census."""
from pathlib import Path
import json
BASE=Path(__file__).resolve().parent


def main():
    def read(name):return json.loads((BASE/name).read_text(encoding='utf8'))
    m=read('analysis_v1/analysis_complete.json');a=read('analysis_v1/audit.json');done=read('analysis_v1/complete.json')
    summaries=[r['summary'] for r in read('analysis_v1/statistics.json')['by_target']]
    initializations=sum(r['source_nonempty'] for r in summaries)
    matching=sum(r['matching_windows'] for r in summaries);divergences=sum(r['first_rate_divergence'] for r in summaries)
    updates=sum(r['analysis_posterior_updates'] for r in summaries)
    assert m['declarations']==matching+divergences==3027
    assert m['candidate_predictions']==4*m['declarations']==12108
    assert m['arithmetic']['linear_solves']==updates==440
    assert m['arithmetic']['symmetric_eigendecompositions']==3*initializations+12*m['declarations']+3*updates==44148
    assert a['declarations']==m['declarations'] and a['analysis_posterior_updates']==updates and a['arithmetic']['linear_solves']==0
    assert done['wall_ns']<=1800*10**9
    saved=read('cost_reconstruction.json')
    assert saved['main_prior_session_initializations']==initializations and saved['main_matching_feedback_windows']==matching
    assert saved['main_first_divergences']==divergences and saved['complete_analysis_elapsed_ns']==done['wall_ns']
    auxiliary=read('runtime_diagnostic_v1/receipt.json')
    assert auxiliary['model_declarations']==2 and auxiliary['candidate_predictions']==8 and auxiliary['posterior_updates']==0
    assert auxiliary['symmetric_eigendecompositions_reconstructed_from_code']==2*(3+8+4)==30
    print(json.dumps(dict(integrity='PASSED_LITERAL_COST_RECONSTRUCTION',main_declarations=3027,main_updates=440,
        main_eigen=44148,auxiliary_synthetic_declarations=2,auxiliary_code_reconstructed_eigen=30,
        whole_analysis_wall_budget_passed=True,new_physics=0,online_LLM_API_calls=0)),flush=True)


if __name__=='__main__':main()
