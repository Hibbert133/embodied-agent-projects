"""Standalone static scientific figure; isolated plotting dependencies."""
from pathlib import Path
import json,os,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/packages')
os.environ['MPLCONFIGDIR']=r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/mpl_cache'
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
font_manager.fontManager.addfont(r'C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'svg.hashsalt':'learned-native-v1'})
run=Path(sys.argv[1]).resolve().parent;out=run/'result_delivery/figures';out.mkdir(exist_ok=False)
r=json.loads((run/'result_delivery/results.json').read_text('utf8'))
signal=json.loads((run/'training_signal/analysis.json').read_text('utf8'))
names=['LEGACY_REFERENCE','DYNAMIC_FORCED_REFERENCE','LEARNED_JOINT_BANK0'];labels=['旧程序参考','新接口强制参考','冻结学习模型'];colors=['#6F7B87','#36A7B8','#DB7549']
fig,axes=plt.subplots(2,2,figsize=(13,8.6),layout='constrained')
fig.suptitle('原生接入负结果与旧 TRAIN 信号诊断\n补充核验通过；完整神经 MOVE 链路 0；不作任务收益资格',fontsize=16)
ax=axes[0,0];values=[r['programs'][n]['mean_deadline_loss'] for n in names]
bars=ax.bar(range(3),values,color=colors,width=.65)
for i,b in enumerate(bars):
    row=r['programs'][names[i]];ax.text(b.get_x()+b.get_width()/2,b.get_height()+5,f"{values[i]:.2f}\n成功 {row['success']}/{row['n']}",ha='center',fontsize=10)
ax.set(xticks=range(3),xticklabels=labels,ylabel='平均截止损失（步，越低越好）',ylim=(0,max(values)*1.3+10),title='54 次执行：每程序 18 例，全部保留')
ax=axes[0,1]
for p,c,label in zip(names,colors,labels):ax.plot(range(3),[g['programs'][p]['mean_deadline_loss'] for g in r['groups']],marker='o',label=label,color=c,linewidth=2,alpha=.85)
ax.set(xticks=range(3),xticklabels=['组 0 / 边界16','组 1 / 边界32','组 2 / 边界64'],ylabel='组内平均截止损失（步）',title='3 个新组；固定参考随边界轮换')
ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
ax=axes[1,0];m=r['signal']['overall']['equal_group_means'];v=[m['error'],m['command_energy'],m['motion_energy'],-m['alignment']]
ax.bar(range(4),v,color=['#6C68A4','#399C83','#60A7C4','#BD6C6C']);ax.axhline(0,color='#777777',lw=.8)
for i,x in enumerate(v):ax.text(i,x+(.025 if x>=0 else -.025),f'{x:.3f}',ha='center',va='bottom' if x>=0 else 'top')
ax.set(xticks=range(4),xticklabels=['观测误差 E','命令能量 U','运动能量 D','对齐项 −C'],ylabel='按轨迹再按组平均',ylim=(-1.15,1.0),title='旧 TRAIN：E = U + D − C（代数，不是因果分解）')
ax=axes[1,1];y=[signal['groups'][str(g)]['relative_command_only_l2_mean'] for g in range(9)]
ax.bar(range(9),y,color='#6C68A4',alpha=.8);ax.axhline(1,color='#888888',ls='--',lw=1,label='相对误差 = 1（展示参照）')
ax.set(xticks=range(9),xlabel='源 TRAIN 独立组',ylabel='||E - U||2 / ||E||2 的轨迹平均',title='以命令能量替代误差并不准确：完整 536 窗口')
ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
for suffix in ('png','pdf','svg'):fig.savefig(out/('native_and_signal.'+suffix),dpi=180,metadata={'Creator':'frozen native diagnostic'})
p=out/'native_and_signal.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text('utf8').splitlines())+'\n',encoding='utf8',newline='\n')
print(str(out/'native_and_signal.png'))
