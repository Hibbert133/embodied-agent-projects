"""Descriptive figure only; source values remain group weighted."""
from pathlib import Path
import sys,os,json
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(Path(__file__).parent/'correction_scope_plotting_v1/packages'))
os.environ['MPLCONFIGDIR']=str(Path(__file__).parent/'controller_agreement_mplconfig_v1')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
p=ROOT/'outputs/controller_agreement/feasibility_v1';rows=list(io.rows(p/'pairs.jsonl.gz'));s=io.read(p/'summary.json')
font=FontProperties(fname=r'C:/Windows/Fonts/msyh.ttc')
fig,axes=plt.subplots(1,2,figsize=(12.8,4.8));fig.subplots_adjust(left=.08,right=.97,bottom=.20,top=.78,wspace=.42)
counts=[sum(r['missing_reason'] is not None for r in rows),sum(r['matched_steps']==0 for r in rows),
    sum(r['matched_steps'] is not None and r['matched_steps']>0 and r['status']=='FIRST_DISAGREEMENT' for r in rows),
    sum(r['status']=='MATCHED_TO_TERMINAL' for r in rows)]
labels=['采用前结束','首命令分歧','延后分歧','匹配至终局']
bars=axes[0].bar(range(4),[100*n/len(rows) for n in counts],color=['#adb5bd','#d36a3b','#5b8db8','#5c9b78'])
axes[0].set_xticks(range(4),labels,fontproperties=font,fontsize=10);axes[0].set_ylim(0,100)
axes[0].set_ylabel('完整有向配对分母（%）',fontproperties=font);axes[0].set_title('首个命令已区分绝大多数候选',fontproperties=font,fontsize=12)
for b,n in zip(bars,counts):axes[0].text(b.get_x()+b.get_width()/2,b.get_height()+2,f'{n:,}\n{100*n/len(rows):.2f}%',ha='center',va='bottom',fontsize=9)
names=[];values=[]
for task,label in [('push-v3','推物'),('reach-v3','到达'),('door-open-v3','开门')]:
    for c,clabel in [('UNCHANGED','不变'),('CHANGED','变化')]:
        g=[]
        for group in range(9):
            data=[r for r in rows if r['task']==task and r['context']==c and r['group']==group and r['missing_reason'] is None]
            if data:g.append(sum(r['loss_delta_interval'][1]-r['loss_delta_interval'][0] for r in data)/len(data))
        names.append(label+' / '+clabel);values.append(sum(g)/len(g) if g else None)
assert all(v is not None for v in values)
bars=axes[1].barh(range(6),values,color='#5b8db8');axes[1].set_yticks(range(6),names,fontproperties=font,fontsize=10);axes[1].invert_yaxis();axes[1].set_xlim(0,525)
axes[1].set_xlabel('完整截止损失差范围宽度（步）',fontproperties=font);axes[1].set_title('有入口的保守范围仍很宽',fontproperties=font,fontsize=12)
for b,v in zip(bars,values):axes[1].text(v+4,b.get_y()+b.get_height()/2,f'{v:.1f}',va='center',fontsize=9)
for ax in axes:ax.spines[['top','right']].set_visible(False)
fig.suptitle('共同前缀复用：TRAIN 全人口描述，非新方法收益',fontproperties=font,fontsize=16,y=.97)
fig.text(.5,.025,'1,944个有向配对 / 9个独立组；右图先配对、后组等权；相反方向不是独立样本',ha='center',fontproperties=font,fontsize=10)
target=p/'presentation/controller_agreement_v1.png';fig.savefig(target,dpi=180);plt.close(fig)
report=ROOT/'reports/controller_agreement_v1_zh.md';text=report.read_text('utf8');needle='## 全部任务与条件'
text=text.replace(needle,'![描述性共同前缀与范围](../outputs/controller_agreement/feasibility_v1/presentation/controller_agreement_v1.png)\n\n'+needle)
report.write_text(text,encoding='utf8',newline='\n')
print(target)
