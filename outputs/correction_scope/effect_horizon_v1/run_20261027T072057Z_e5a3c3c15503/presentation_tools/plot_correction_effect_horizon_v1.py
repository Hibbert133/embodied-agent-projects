"""Observed-input consistency and support; no entry forecast claims."""
from pathlib import Path
import os,json,sys
sys.path.insert(0,r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/packages')
os.environ['MPLCONFIGDIR']=r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/mpl_cache'
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
font_manager.fontManager.addfont(r'C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'svg.hashsalt':'effect-horizon-v1'})
run=Path(sys.argv[1]).resolve().parent;out=run/'presentation/figures';out.mkdir(exist_ok=True)
panels=json.loads((run/'analysis/panels.json').read_text('utf8'));totals=sorted([p for p in panels if not p['axes']],key=lambda p:p['horizon']);h=[p['horizon'] for p in totals]
fig,(ax,support)=plt.subplots(1,2,figsize=(12.8,7.4),gridspec_kw={'width_ratios':[1.05,1]})
fig.subplots_adjust(left=.08,right=.98,top=.8,bottom=.28,wspace=.28)
fig.suptitle('纠正分歧后的事实连续窗口\n事后使用真实未来输入；不是入口预测或任务资格',fontsize=15,y=.96)
for kind,label,color in [('ZERO_EFFECT','零效应','#999999'),('NOMINAL_SENT','名义发送命令和','#BE6949'),('FROZEN_GLOBAL_MATRIX','冻结全局矩阵','#287F79')]:
    ax.plot(h,[10*np.sqrt(p['mse'][kind]) for p in totals],marker='o',color=color,label=label)
ax.set(xscale='log',yscale='log',xticks=h,xticklabels=h,xlabel='从首次命令分歧起实际完成的控制步H',ylabel='XY RMSE（mm，对数轴）',title='每个H内按独立组分层等权')
ax.legend(fontsize=9);ax.grid(alpha=.2,which='both')
statuses=[('COMPLETE_FACTUAL_WINDOW','完整窗口','#287F79'),('BEFORE_DECISION_TERMINAL','决策前结束','#B6C5D5'),('ACQUISITION_TERMINAL','获取中结束','#DBBDA4'),('NO_SENT_DIFFERENCE','没有命令分歧','#888888'),('SOURCE_A_SHORT','A来源短','#B38CB7'),('SOURCE_B_SHORT','B来源短','#D5A778'),('BOTH_SOURCES_SHORT','两来源均短','#C66B60')]
base=np.zeros(6);positions=np.arange(6)
for key,label,color in statuses:
    values=np.asarray([p['statuses'].get(key,0) for p in totals]);support.bar(positions,values,bottom=base,label=label,color=color,width=.7);base+=values
assert (base==972).all()
support.set(xticks=positions,xticklabels=h,xlabel='窗口H',ylabel='全部972登记率对',ylim=(0,1030),title='固定完整分母；缺失不填零误差\n柱顶数字为实际完整窗口数')
for i,p in enumerate(totals):support.text(i,985,str(p['available']),ha='center',fontsize=9)
handles,labels=support.get_legend_handles_labels();fig.legend(handles,labels,ncol=4,loc='lower center',bbox_to_anchor=(.5,.11),frameon=False,fontsize=9)
fig.text(.5,.025,'长窗口可用人口会改变，分歧后状态、原政策、Z和夹爪也可变化；不能从趋势唯一归因延迟或物理模型。',ha='center',fontsize=9)
for suffix in ('png','pdf','svg'):fig.savefig(out/('effect_horizon.'+suffix),dpi=180,metadata={'Creator':'factual input-conditioned horizon diagnosis'})
p=out/'effect_horizon.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text('utf8').splitlines())+'\n',encoding='utf8',newline='\n')
print(str(out/'effect_horizon.png'))
