from pathlib import Path
import sys,os,math
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT));ext=Path(__file__).parent
sys.path.insert(0,str(ext/'correction_scope_plotting_v1/packages'));os.environ['MPLCONFIGDIR']=str(ext/'mpl_cache')
from src.analysis import packet_structure_sources_v1 as a
from src.analysis.release_learning_guard_v1 import read_only


def plot(path):
    a.checked(path);run=path.parent;out=run/'presentation';guard={}
    with read_only(guard):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.font_manager import FontProperties
        font=FontProperties(fname=r'C:\Windows\Fonts\msyh.ttc');plt.rcParams['font.family']=font.get_name();plt.rcParams['axes.unicode_minus']=False
        m=a.io.read(run/'analysis/prediction_panels.json');r=a.io.read(run/'analysis/observed_panels.json');fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained');series=[]
        for method,style in zip(a.METHODS,('--','-','-','--',':')):
            y=[math.sqrt(max(0,next(p['mean']['saved_pair_mse_m2'] for p in m if p['level']==['split','horizon'] and p['strata']==dict(split='QUAL',horizon=h) and p['method']==method)))*1000 for h in range(1,17)]
            axes[0].plot(range(1,17),y,style,label=method,linewidth=1.8);series.append(dict(panel='QUAL_SAVED_MSE_RMS',method=method,mm=y))
        for split,style in zip(a.original.SPLITS,('-','--','-.',':')):
            y=[math.sqrt(max(0,next(p['mean']['linear_command_class_floor_m2'] for p in r if p['level']==['split','horizon'] and p['strata']==dict(split=split,horizon=h))))*1000 for h in range(1,17)]
            axes[1].plot(range(1,17),y,style,label=split,linewidth=1.8);series.append(dict(panel='OBSERVED_EVEN_FLOOR_RMS',split=split,mm=y))
            if split=='QUAL':axes[0].plot(range(1,17),y,'k--',label='观测偶分量下界',linewidth=2)
        for ax,title in zip(axes,('QUAL：全部五个保存预测与偶分量下界','四个分割：全部 H 的观测偶分量下界')):
            ax.set_xlabel('真实包内控制步 H');ax.set_ylabel('平方根（组等权 MSE），mm');ax.set_title(title,fontsize=11);ax.set_xticks((1,4,8,12,16));ax.set_ylim(bottom=0);ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle('事后描述性结构分解：不同于原资格平均 RMSE\n零新增环境交互 / 拟合 / 模型预测；原 CLOSED_NEGATIVE 保留',fontsize=12)
        fig.savefig(out/'structure.png',dpi=150);fig.savefig(out/'structure.svg');plt.close(fig)
        svg=out/'structure.svg';svg.write_bytes(('\n'.join(line.rstrip() for line in svg.read_text('utf8').splitlines()).rstrip()+'\n').encode('utf8'))
    a.io.write(out/'figure_receipt.json',dict(status='RENDERED_PENDING_VISUAL_CHECK',series=series,guard=guard,source_panels_sha256={n:a.io.sha(run/'analysis'/n) for n in ('observed_panels.json','prediction_panels.json')},
        output_sha256={n:a.io.sha(out/n) for n in ('structure.png','structure.svg')},new_physics=0,new_fits=0,new_predictions=0,online_LLM_API_calls=0))


if __name__=='__main__':plot(Path(sys.argv[1]).resolve())
