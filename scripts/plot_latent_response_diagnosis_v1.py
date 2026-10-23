"""Standard scientific plots from audited descriptive tables, isolated report Python."""
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import argparse,json,sys,hashlib,socket
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def plot(folder,out):
    start=perf_counter_ns();out.mkdir(exist_ok=False);objectives=read(folder/'TRAIN_objectives.json');broad=read(folder/'broad_grouped_metrics.json')
    methods=('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8');tasks=('push-v3','reach-v3','door-open-v3')
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    for ax,task in zip(axes,tasks):
        for method in methods:
            rs=sorted((r for r in objectives if r['task']==task and r['method']==method and r['regime']=='ALL_WINDOWS'),key=lambda r:r['checkpoint'])
            ax.plot([r['checkpoint'] for r in rs],[r['metrics']['masked_H8_objective_m2']*1e6 for r in rs],marker='o',label=method)
        ridge=next(r for r in objectives if r['task']==task and r['method']=='DIRECT_RIDGE_H8' and r['regime']=='ALL_WINDOWS')
        ax.axhline(ridge['metrics']['masked_H8_objective_m2']*1e6,ls='--',color='black',label='DIRECT_RIDGE fixed')
        ax.set_yscale('log');ax.set_title(task);ax.set_xlabel('Saved TRAIN update (no checkpoint selection)');ax.set_ylabel('Exact sampler objective (mm^2)');ax.grid(alpha=.25)
    axes[-1].legend(fontsize=7);fig.tight_layout();fig.savefig(out/'TRAIN_fixed_checkpoints.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    for ax,task in zip(axes,tasks):
        for method in (*methods,'DIRECT_RIDGE_H8','PERSIST_ZERO','HISTORY_LINEAR10','QUADRATIC_STATE20'):
            r=next(r for r in broad if r['split']=='QUAL' and r['task']==task and r['method']==method and r['checkpoint']==(5000 if method in methods else None) and r['regime']=='ENTRY_ONLY')
            v=r['metrics']['horizon_mse_m2'];ax.plot(range(1,9),[np.sqrt(x)*1000 if x is not None else np.nan for x in v],marker='.',label=method)
        ax.set_title(task);ax.set_xlabel('Actual horizon');ax.set_ylabel('Root of group-mean horizon MSE (mm)');ax.grid(alpha=.25)
    axes[-1].legend(fontsize=7);fig.suptitle('QUAL saved entry forecasts; group weighting; descriptive only');fig.tight_layout();fig.savefig(out/'QUAL_actual_horizons.png',dpi=160);plt.close(fig)
    units=read(folder/'reference_menu_units.json');fig,axes=plt.subplots(2,1,figsize=(16,7),sharex=True);x=np.arange(54)
    for method in ('RAW_CONTINUE','LOCAL_PID_KEEP','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET_NO_PROBE'):
        axes[0].plot(x,[r['menu_losses'][method] for r in units],marker='.',lw=.9,label=method)
    axes[0].set_ylabel('Full recorded cutoff loss (steps)');axes[0].legend(fontsize=7,ncol=3);axes[0].grid(alpha=.25)
    axes[1].bar(x,[r['optimistic_raw_saving'] for r in units],label='Eight-program realized-future oracle',color='tab:blue')
    axes[1].plot(x,[r['same_acquisition_optimistic_raw_saving'] for r in units],marker='.',lw=1,color='tab:orange',label='Four-program adoption submenu oracle')
    axes[1].set_ylabel('Optimistic saving vs RAW (steps)');axes[1].set_xlabel('All 54 recorded task/context units, six per independent group');axes[1].set_xticks(np.arange(2.5,54,6),[f'Group {g}' for g in range(9)]);axes[1].legend(fontsize=8);axes[1].grid(alpha=.25)
    fig.suptitle('Future-aware record menu is not a deployable policy or learnability proof');fig.tight_layout();fig.savefig(out/'reference_full_cost_opportunity.png',dpi=160);plt.close(fig)
    value={'integrity':'PLOTTED_AUDITED_TABLES','python':sys.executable,'python_sha256':sha(sys.executable),'matplotlib_version':matplotlib.__version__,
        'matplotlib_init_sha256':sha(matplotlib.__file__),'numpy_version':np.__version__,'worker_sha256':sha(__file__),
        'input_sha256':{p.name:sha(p) for p in (folder/'TRAIN_objectives.json',folder/'broad_grouped_metrics.json',folder/'reference_menu_units.json')},
        'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0}
    with (out/'runtime.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')
    print(value,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);v=p.parse_args()
    def denied(*args,**kwargs):raise RuntimeError('No network in report plotting')
    with patch.object(socket.socket,'connect',denied),patch.object(socket.socket,'connect_ex',denied),patch.object(socket,'create_connection',denied):plot(v.analysis.resolve(),v.output.resolve())
