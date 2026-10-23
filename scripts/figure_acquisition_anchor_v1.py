"""All 18 assigned movement panels from audited exports; static research figure."""
from pathlib import Path
from collections import defaultdict
from time import perf_counter_ns
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_anchor_diagnosis_io_v1 as s
io=s.io


def main(path):
    start=perf_counter_ns();path=path.resolve();s.checked(path);out=path.parent;a=io.read(out/'audit.json');io.require(a['integrity']=='PASSED','audited exports only')
    for n,h in a['artifact_sha256'].items():io.require(io.sha(out/n)==h,'audited figure data changed')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    font=Path('C:/Windows/Fonts/msyh.ttc');io.require(font.exists(),'Chinese figure font required')
    fm.fontManager.addfont(str(font));plt.rcParams['font.family']=fm.FontProperties(fname=str(font)).get_name();plt.rcParams['axes.unicode_minus']=False
    bycase=defaultdict(list)
    for r in io.rows(out/'step_diagnostics.jsonl.gz'):
        if r['relocation'] is not None:bycase[(r['task'],r['context'],r['group'])].append(r['relocation'])
    moves=[v for v in io.read(out/'trajectory_diagnostics.json') if v['action']=='MOVE_MEASURE8'];ceiling=max(v['after_gates']['position_error_inf_m']*1000 for values in bycase.values() for v in values)*1.05
    fig,axes=plt.subplots(3,6,figsize=(19,9),sharex=True,sharey=True,constrained_layout=True)
    tasks=('push-v3','reach-v3','door-open-v3');labels={'push-v3':'推物','reach-v3':'到达','door-open-v3':'开门'}
    for row,task in enumerate(tasks):
        for col,(g,ctx) in enumerate(( (g,c) for g in (0,1,2) for c in ('UNCHANGED','CHANGED') )):
            ax=axes[row,col];values=bycase[(task,ctx,g)];case=next(v for v in moves if (v['task'],v['context'],v['group'])==(task,ctx,g))
            if row==0:ax.set_title(f'{(16,32,64)[g]}步 · '+('不变' if ctx=='UNCHANGED' else '变化'))
            if col==0:ax.set_ylabel(labels[task]+'\n位置最大轴误差（mm）')
            if row==2:ax.set_xlabel('实际移动步')
            ax.set_xlim(0,64);ax.set_ylim(0,max(20,ceiling));ax.grid(alpha=.18)
            if values:
                lift=[v['index'] for v in values if v['stage']=='LIFT']
                if lift:ax.axvspan(0,max(lift),color='#e5e7eb',alpha=.7)
                ax.plot([v['index'] for v in values],[v['after_gates']['position_error_inf_m']*1000 for v in values],color='#2458a6',lw=1.5)
                ax.axhline(15,color='#b91c1c',ls='--',lw=1)
                gate=case['final_relocation_gates'];fail='+'.join(gate['failed_conditions']) or 'READY'
                ax.text(.03,.94,f'n={len(values)}\n{fail}',transform=ax.transAxes,va='top',fontsize=8)
            else:ax.text(.5,.5,'介入前成功\n无移动记录',ha='center',va='center',transform=ax.transAxes,color='#555555')
    fig.suptitle('全部18个分配移动案例：位置误差与固定15mm进入条件\n灰底为抬升阶段；完整进入还要求历史长度、稳定运动与手物间距。全部为事后描述性分析。',fontsize=13)
    folder=out/'figures';folder.mkdir(exist_ok=False)
    fig.savefig(folder/'all_18_assigned_moves.png',dpi=150);fig.savefig(folder/'all_18_assigned_moves.svg');plt.close(fig)
    io.write(out/'figure_receipt.json',{'integrity':'GENERATED_REQUIRES_VISUAL_REVIEW','panels':18,'actual_move_panels':len([v for v in bycase.values() if v]),
        'source_audit_sha256':io.sha(out/'audit.json'),'generator_sha256':io.sha(__file__),'font':str(font),'matplotlib_version':matplotlib.__version__,
        'python':sys.version,'wall_ns':perf_counter_ns()-start,'output_sha256':{p.relative_to(out).as_posix():io.sha(p) for p in folder.iterdir()},
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0})
    print({'panels':18,'figure_directory':str(folder)},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();network={}
    with io.forbid_online_calls(network):main(v.manifest)
    io.write(v.manifest.parent/'figure_network_guard.json',{'integrity':'PASSED','network':network,'new_online_LLM_API_calls':0,'scope':'Static plotting only; no simulator or fitting imported/called'})
