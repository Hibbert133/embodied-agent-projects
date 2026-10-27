"""Fixed complete five-reference presentation; no scoring/model recomputation."""
from pathlib import Path
import os,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
EXTERNAL=Path(__file__).parent;sys.path.insert(0,str(EXTERNAL/'correction_scope_plotting_v1/packages'));os.environ['MPLCONFIGDIR']=str(EXTERNAL/'mpl_cache')
from src.analysis import paired_packet_io_v1 as a
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
        panels=a.io.read(run/'qual_evaluation/panels.json');result=a.io.read(run/'qual_evaluation/result.json');methods=['ZERO','INSTANT','FIR','CENTERED_FIR','FREE_CAUSAL']
        fig,axes=plt.subplots(1,2,figsize=(13,5.8),layout='constrained');meta=[]
        for ax,field,title in zip(axes,('mean_endpoint_loss_m','available_only_mean_endpoint_loss_m'),('完整人口：缺失/无效端点罚 1m','可用窗口：仅作描述，包含生存选择')):
            for k,h in enumerate((8,16)):
                part=[next(p for p in panels if p['level']==['horizon'] and p['strata']==dict(horizon=h) and p['method']==method) for method in methods]
                values=[p[field]*1000 for p in part];xx=[j+(-.18 if k==0 else .18) for j in range(5)];bars=ax.bar(xx,values,width=.34,label='H'+str(h),color=('#377eb8','#ff7f00')[k]);meta.append(dict(field=field,horizon=h,methods=methods,values_mm=values))
                ax.bar_label(bars,labels=[f'{v:.4f}' for v in values],fontsize=7,padding=3,rotation=90)
            ax.set_xticks(range(5),methods,rotation=24,ha='right',fontsize=9);ax.set_ylabel('组等权平均端点 XY RMSE（mm）');ax.set_title(title,fontsize=11);ax.set_ylim(bottom=0,top=ax.get_ylim()[1]*1.25);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(loc='upper left')
        fig.suptitle('已知16步命令包响应差异：独立 QUAL 九组\n全局选定 '+result['selected_model']+'；状态 '+result['status'],fontsize=12)
        fig.savefig(out/'qualification.png',dpi=150);fig.savefig(out/'qualification.svg');plt.close(fig)
        svg=out/'qualification.svg';svg.write_bytes(('\n'.join(line.rstrip() for line in svg.read_text('utf8').splitlines()).rstrip()+'\n').encode('utf8'))
    a.io.write(out/'figure_receipt.json',dict(status='RENDERED_PENDING_VISUAL_CHECK',plotted_saved_panel_values=meta,guard=guard,source_panels_sha256=a.io.sha(run/'qual_evaluation/panels.json'),
        output_sha256={n:a.io.sha(out/n) for n in ('qualification.png','qualification.svg')},new_model_fits=0,new_environment_steps=0,online_LLM_API_calls=0))


if __name__=='__main__':plot(Path(sys.argv[1]).resolve())
