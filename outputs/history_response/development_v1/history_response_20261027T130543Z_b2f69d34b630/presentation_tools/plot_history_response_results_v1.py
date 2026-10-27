"""Plot saved independent scores only, with complete and observed denominators."""
from pathlib import Path
import os,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
EXTERNAL=Path(__file__).parent;sys.path.insert(0,str(EXTERNAL/'correction_scope_plotting_v1/packages'));os.environ['MPLCONFIGDIR']=str(EXTERNAL/'mpl_cache')
from src.analysis import history_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only

def plot(path):
    a.checked(path);run=path.parent;out=run/'presentation';guard={}
    if not (run/'qual_evaluation/result.json').exists():return
    with read_only(guard):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.font_manager import FontProperties
        font=FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc');plt.rcParams['font.family']=font.get_name();plt.rcParams['axes.unicode_minus']=False
        panels=a.io.read(run/'qual_evaluation/panels.json');result=a.io.read(run/'qual_evaluation/result.json')
        methods=['ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN','HISTORY_KERNEL'];labels=['ZERO','INSTANT','FIR','STATE','HIST NN','HIST KERNEL'];meta=[]
        fig,axes=plt.subplots(1,3,figsize=(17,5.6),layout='constrained')
        for ax,field,title in zip(axes[:2],('mean_endpoint_loss_m','available_only_mean_endpoint_loss_m'),('完整分配：含缺失罚1m','可用窗口：仅描述，存在生存选择')):
            part=[next(p for p in panels if p['level']==[] and p['method']==method) for method in methods]
            values=[p[field]*1000 if p[field] is not None else float('nan') for p in part]
            bars=ax.bar(range(6),values,color=['#5386b4']*5+['#cc7138'])
            ax.bar_label(bars,labels=['缺失' if p[field] is None else f'{v:.4f}' for p,v in zip(part,values)],padding=3,fontsize=8,rotation=45)
            ax.set_xticks(range(6),labels,rotation=26,ha='right',fontsize=9);ax.set_ylabel('组等权平均端点损失(mm)');ax.set_title(title,fontsize=11)
            ax.set_ylim(0,ax.get_ylim()[1]*1.22);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
            meta.append(dict(field=field,methods=methods,values_mm=[None if p[field] is None else p[field]*1000 for p in part]))
        ax=axes[2];names=[];deltas=[]
        for i,(name,row) in enumerate(result['co_primary'].items()):
            lo,hi=[v*1000 for v in row['bootstrap95_m']];mean=row['mean_difference_m']*1000
            color='#2b7a55' if hi<0 else '#b24d49' if lo>0 else '#6c7180'
            ax.hlines(i,lo,hi,color=color,linewidth=2);ax.scatter([mean],[i],color=color,s=34,zorder=3);names.append(name)
            deltas.append(dict(baseline=name,mean_mm=mean,bootstrap95_mm=[lo,hi]))
        ax.axvline(0,color='#444',linestyle='--',linewidth=1);ax.set_yticks(range(len(names)),names,fontsize=9);ax.invert_yaxis()
        ax.set_xlabel('HISTORY_KERNEL − 参考 (mm)，小于0较好');ax.set_title('五个主比较：独立组95%区间',fontsize=11);ax.grid(axis='x',alpha=.2)
        fig.suptitle('公开历史条件响应：独立QUAL九组\n'+result['status']+'；预测组件，非完整任务损失或安全保证',fontsize=12)
        fig.savefig(out/'qualification.png',dpi=170);fig.savefig(out/'qualification.svg');plt.close(fig)
        svg=out/'qualification.svg';svg.write_bytes(('\n'.join(line.rstrip() for line in svg.read_text('utf8').splitlines()).rstrip()+'\n').encode('utf8'))
    a.io.write(out/'figure_receipt.json',dict(status='RENDERED_PENDING_VISUAL_CHECK',plotted_saved_panels=meta,plotted_saved_contrasts=deltas,guard=guard,
        source_panels_sha256=a.io.sha(run/'qual_evaluation/panels.json'),source_result_sha256=a.io.sha(run/'qual_evaluation/result.json'),
        output_sha256={n:a.io.sha(out/n) for n in ('qualification.png','qualification.svg')},new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0))

if __name__=='__main__':plot(Path(sys.argv[1]).resolve())
