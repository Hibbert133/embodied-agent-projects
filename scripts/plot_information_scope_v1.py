"""Plot already-audited finite arrays in the isolated presentation runtime."""
from pathlib import Path
import argparse,hashlib,json,socket
from unittest.mock import patch
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def plot(root,out):
    out.mkdir(exist_ok=False);rows=read(root/'planning/probability_results.json');w=read(root/'planning/witness.json')['result']
    fig,ax=plt.subplots(figsize=(8,5))
    for family,label in [('SAME_FINE_POSTERIOR_DIFFERENT_PREDICTIVE','Same fine posterior; predictive mismatch'),('MATCHED_PREDICTIVE_POSITIVE_CONTROL','Matched predictive marginal control')]:
        rs=[v for v in rows if v['family']==family]
        ax.scatter([v['predictive_slack'] for v in rs],[v['posterior_penalty_increase'] for v in rs],s=18,alpha=.5,label=label)
    ax.axhline(0,color='gray',ls=':');upper=max(v['predictive_slack'] for v in rows)
    ax.plot([0,upper],[0,upper],ls='--',color='black',label='Corrected upper bound')
    ax.scatter([w['predictive_slack']],[w['posterior_penalty_increase']],marker='*',s=160,color='red',label='Explicit positive-support witness')
    ax.set_xlabel('Predictive marginal KL contraction (nats)');ax.set_ylabel('Conditional posterior KL increase (nats)')
    ax.set_title('Constructed finite laws; no independent robot samples');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(out/'conditional_and_joint_scope.png',dpi=160);plt.close(fig)
    problems=read(root/'planning/decision_problems.json');values=read(root/'evaluation/results.json')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    methods=('WORKING_BAYES','ORACLE_JOINT_IMPLEMENTED','ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH','WORKING_IGNORE_STATE','DIRECT_100')
    for ax,shift in zip(axes,(-5,0,20)):
        ps=[p for p in problems if p['direction']=='FORWARD' and p['fine_shift']==0 and p['coarse_shift']==shift and p['coarse_cost']==1]
        for method in methods:
            y=[next(v['cutoff_loss'] for v in values if v['problem_id']==p['problem_id'] and v['method']==method) for p in ps]
            ax.plot([p['fine_cost'] for p in ps],y,marker='o',label=method,lw=1.3)
        ax.set_title(f'Coarse poststate shift = {shift}');ax.set_xlabel('Fine acquisition synthetic cost');ax.set_ylabel('Exact expected full cutoff loss');ax.grid(alpha=.25)
    axes[-1].legend(fontsize=6.8);fig.suptitle('Diagnostic slice; all 216 constructed problems remain in the report')
    fig.tight_layout();fig.savefig(out/'implemented_continuation_costs.png',dpi=160);plt.close(fig)
    with (out/'runtime.json').open('x',encoding='utf-8',newline='\n') as handle:
        json.dump(dict(matplotlib_version=matplotlib.__version__,worker_sha256=sha(Path(__file__)),
            input_sha256={p.relative_to(root).as_posix():sha(p) for p in (root/'planning/probability_results.json',root/'planning/witness.json',root/'planning/decision_problems.json',root/'evaluation/results.json')},
            new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0),handle,indent=2);handle.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);v=p.parse_args()
    def deny(*args,**kwargs):raise RuntimeError('No network in finite report plot worker')
    with patch.object(socket.socket,'connect',deny),patch.object(socket,'create_connection',deny):plot(v.root.resolve(),v.output.resolve())
