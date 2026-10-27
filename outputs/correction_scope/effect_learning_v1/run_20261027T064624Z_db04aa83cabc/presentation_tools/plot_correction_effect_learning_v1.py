"""Descriptive prediction plots; overlapping LOO folds have no invented CIs."""
from pathlib import Path
import json,os,sys
sys.path.insert(0,r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/packages')
os.environ['MPLCONFIGDIR']=r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/mpl_cache'
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
font_manager.fontManager.addfont(r'C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'svg.hashsalt':'correction-effect-learning-v1'})
run=Path(sys.argv[1]).resolve().parent;out=run/'presentation/figures';out.mkdir(exist_ok=False)
panels=json.loads((run/'evaluation/panels.json').read_text('utf8'));extra=json.loads((run/'presentation/additional_panels.json').read_text('utf8'))
methods=['ZERO_EFFECT','NOMINAL_SENT','GLOBAL_SCALAR','GLOBAL_MATRIX','ABSOLUTE_CONTEXT','PAIRED_CONTEXT']
labels=['零效应','名义发送差','全局标量','全局矩阵','绝对位移回归','成对上下文回归']
colors=['#999999','#BE6949','#C8AA62','#497E9D','#8A6CA2','#238A71']
fig,(ax,bottom)=plt.subplots(2,1,figsize=(12.6,9.2),gridspec_kw={'height_ratios':[1.35,1]})
fig.subplots_adjust(left=.09,right=.98,top=.88,bottom=.18,hspace=.38)
fig.suptitle('同状态首次真实命令分歧：响应差预测\n旧TRAIN的整组留出开发；不是任务收益或独立部署资格',fontsize=15,y=.97)
top=[next(p for p in panels if not p['axes'])]+[p for p in panels if p['axes']==['task']]
x=np.arange(len(top));width=.125
for j,kind in enumerate(methods):
    values=[p['mse'][kind] for p in top];assert min(values)>0
    ax.bar(x+(j-2.5)*width,values,width=width,color=colors[j],label=labels[j])
ax.set(yscale='log',xticks=x,xticklabels=['整体']+[p['values'][0].replace('-v3','') for p in top[1:]],ylabel='XY响应差 MSE（归一化位移平方，对数轴）',title='六个预先固定参考；层级等权后的条件人口')
ax.grid(axis='y',alpha=.2,which='both');ax.set_axisbelow(True)
groups=[p for p in extra if p['axes']==['group']]
for kind in ('ZERO_EFFECT','GLOBAL_MATRIX','ABSOLUTE_CONTEXT','PAIRED_CONTEXT'):
    j=methods.index(kind);bottom.plot([p['values'][0] for p in groups],[p['mse'][kind] for p in groups],marker='o',lw=1.5,color=colors[j],label=labels[j])
bottom.set(yscale='log',xticks=list(range(9)),xlabel='留出的完整TRAIN组（各折训练集重叠）',ylabel='组内效应 MSE（对数轴）',title='全部9组；折数不作为独立最终资格样本数')
bottom.grid(axis='y',alpha=.2,which='both')
handles,_=ax.get_legend_handles_labels();fig.legend(handles,labels,ncol=3,loc='lower center',bbox_to_anchor=(.5,.075),frameon=False)
fig.text(.5,.025,'只评价两条实际执行命令首次分歧的响应；无分歧/提前结束不补零；完整972对与324分层单元随报告保留。',ha='center',fontsize=9)
for suffix in ('png','pdf','svg'):fig.savefig(out/('effect_prediction.'+suffix),dpi=180,metadata={'Creator':'paired effect descriptive development'})
p=out/'effect_prediction.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text('utf8').splitlines())+'\n',encoding='utf8',newline='\n')
print(str(out/'effect_prediction.png'))
