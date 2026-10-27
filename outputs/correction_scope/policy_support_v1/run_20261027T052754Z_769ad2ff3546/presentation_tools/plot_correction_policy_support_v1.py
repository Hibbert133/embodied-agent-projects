"""Partial outcome bounds, not confidence intervals or new robot outcomes."""
from pathlib import Path
import json,os,sys
sys.path.insert(0,r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/packages')
os.environ['MPLCONFIGDIR']=r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/correction_scope_plotting_v1/mpl_cache'
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
font_manager.fontManager.addfont(r'C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'svg.hashsalt':'policy-support-v1'})
run=Path(sys.argv[1]).resolve().parent;out=run/'presentation/figures';out.mkdir(parents=True,exist_ok=False)
r=json.loads((run/'analysis/fixed_program_bounds.json').read_text('utf8'))
fig,(ax,group)=plt.subplots(1,2,figsize=(13,7.5),layout='constrained',gridspec_kw={'width_ratios':[1.55,1]})
fig.suptitle('固定程序的事实相容性与未知后缀界限\n事后描述；界限不是置信区间，不是新增部署结果',fontsize=15)
labels=[]
for i,row in enumerate(r):
    y=len(r)-i-1;lo=row['lower_mean'];hi=row['upper_mean'];color='#D56E40' if (row['action'],row['rate'])==('VALIDATE8',.125) else '#388E9A'
    ax.plot([lo,hi],[y,y],color=color,lw=4,solid_capstyle='round');ax.scatter([lo,hi],[y,y],color=color,s=28,zorder=3)
    label={'CONTINUE':'继续','VALIDATE8':'验证8步','MOVE_MEASURE':'移动测量'}[row['action']]
    labels.append(f"{label} / {row['rate']}  [{row['supported']}/18]")
ax.set(yticks=list(range(len(r)-1,-1,-1)),yticklabels=labels,xlabel='完整18单元的平均截止损失范围（步）',title='12个固定程序；方括号为已支持完整结果数',xlim=(0,510),ylim=(-1.4,len(r)-.4))
ax.axvline(1435/18,color='#A75A46',ls='--',lw=1.5,label='模型实际均值 79.72')
ax.axvline(1886/18,color='#777777',ls=':',lw=1.5,label='轮换工程参考 104.78')
ax.grid(axis='x',alpha=.2);ax.legend(loc='lower right',fontsize=8)
primary=next(x for x in r if x['action']=='VALIDATE8' and x['rate']==.125)
for g in primary['groups']:
    i=g['group'];lo=g['lower_mean'];hi=g['upper_mean'];group.plot([i,i],[lo,hi],color='#D56E40',lw=5);group.scatter([i,i],[lo,hi],color='#D56E40',s=35)
    group.text(i+.06,(lo+hi)/2,f"{g['supported']}/6",fontsize=9)
native=json.loads((Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')/'outputs/learned_acquisition/native_v1/run_20261027T042530Z_3c437c6d3f5d/result_delivery/results.json').read_text('utf8'))
group.plot(range(3),[g['programs']['LEARNED_JOINT_BANK0']['mean_deadline_loss'] for g in native['groups']],marker='o',color='#A75A46',ls='--',label='模型各组实际损失')
group.set(xticks=range(3),xticklabels=['组0 / 边界16','组1 / 边界32','组2 / 边界64'],xlim=(-.2,2.35),ylabel='组内平均截止损失（步）',title='主参考：固定VALIDATE8 / .125')
group.grid(axis='y',alpha=.2);group.legend(fontsize=8)
for suffix in ('png','pdf','svg'):fig.savefig(out/('fixed_program_bounds.'+suffix),dpi=180,metadata={'Creator':'policy support descriptive analysis'})
p=out/'fixed_program_bounds.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text('utf8').splitlines())+'\n',encoding='utf8',newline='\n')
print(str(out/'fixed_program_bounds.png'))
