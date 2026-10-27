"""Standalone scientific figure from immutable saved qualification results."""
from pathlib import Path
import os,sys
EXTERNAL=Path(__file__).parent
os.environ['MPLBACKEND']='Agg';os.environ['MPLCONFIGDIR']=str(EXTERNAL/'graybox_plot_cache_v1')
sys.path.insert(0,str(EXTERNAL/'correction_scope_plotting_v1/packages'))
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from src.analysis import graybox_response_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
io=a.io

def plot(path):
    a.checked(path);root=path.parent;out=root/'presentation';guard={};font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    if not (root/'qual_evaluation/result.json').exists():return
    with read_only(guard):
        data=io.read(root/'qual_evaluation/panels.json');global_rows=[p for p in data if not p['level']];names=[p['method'] for p in global_rows]
        fig,axes=plt.subplots(1,2,figsize=(13,4.8),layout='constrained');colors=['#bd5b2c' if n=='GRAY_JOINT' else '#31688e' for n in names]
        for ax,field,title in zip(axes,('mean_endpoint_loss_m','available_only_mean_endpoint_loss_m'),('完整人口（含缺失惩罚）','可用窗口（仅作描述）')):
            ax.barh(names,[float('nan') if p[field] is None else p[field]*1000 for p in global_rows],color=colors);ax.invert_yaxis();ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
            ax.set_title(title,fontproperties=font,fontsize=12);ax.set_xlabel('位置差端点 RMSE（mm，越低越好）',fontproperties=font)
        fig.suptitle('标准响应参考的独立资格；不是完整任务收益',fontproperties=font,fontsize=14)
        fig.savefig(out/'qualification.png',dpi=180);fig.savefig(out/'qualification.svg');plt.close(fig)
    io.write(out/'figure_receipt.json',dict(integrity='GENERATED_PENDING_VISUAL_CHECK',source_panels_sha256=io.sha(root/'qual_evaluation/panels.json'),
        png_sha256=io.sha(out/'qualification.png'),svg_sha256=io.sha(out/'qualification.svg'),read_only_guard=guard,online_LLM_API_calls=0))

if __name__=='__main__':plot(Path(sys.argv[1]).resolve())
