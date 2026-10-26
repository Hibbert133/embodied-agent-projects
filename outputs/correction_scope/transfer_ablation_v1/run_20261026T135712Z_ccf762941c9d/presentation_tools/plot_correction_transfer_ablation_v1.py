from pathlib import Path
from time import perf_counter_ns
import os,sys
HERE=Path(__file__).parent;os.environ['MPLCONFIGDIR']=str(HERE/'mpl_cache');sys.path.insert(0,str(HERE/'correction_scope_plotting_v1/packages'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_transfer_ablation_v1 as m
io=m.io;path=Path(sys.argv[1]).resolve();out=path.parent/'presentation/figures';out.mkdir(parents=True,exist_ok=False)
assert io.read(path.parent/'replay_audit.json')['integrity']=='PASSED';r=io.read(path.parent/'results.json');start=perf_counter_ns()
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'svg.fonttype':'none'})
fig,ax=plt.subplots(1,2,figsize=(14,7),gridspec_kw={'width_ratios':[1.2,1]})
versions=(*m.prior.VARIANTS,*m.KINDS);colors=['#aebac9']*4+['#c95050','#347cab','#65a16e','#a079b6']
names=[];loss=[]
for v in versions:
    s=r['selectors'][v+'/TWO_STAGE'];names.append(v);loss.append(s['mean_loss'])
ax[0].barh(range(8),loss,color=colors);ax[0].set_yticks(range(8),names);ax[0].invert_yaxis();ax[0].set_xlim(0,max(loss)*1.22)
for i,(v,l) in enumerate(zip(versions,loss)):ax[0].text(l+.6,i,f"{l:.3f}；{r['selectors'][v+'/TWO_STAGE']['success']}/54",va='center',fontsize=9)
fixed=min(s['mean_loss'] for k,s in r['selectors'].items() if k.startswith('FIXED/'))
ax[0].axvline(fixed,ls=':',color='#26754e',label='12固定程序的最低全人口均值（事后描述）')
ax[0].set_xlabel('两阶段完整截止损失（步，越低越好）')
handles,legend=ax[0].get_legend_handles_labels();fig.legend(handles,legend,loc='upper center',bbox_to_anchor=(.5,.94),fontsize=9)
candidate=r['selectors']['JOINT_SPO/TWO_STAGE']
for kind,color in zip(m.KINDS,colors[-3:]):
    values=[candidate['groups'][str(g)]-r['selectors'][kind+'/TWO_STAGE']['groups'][str(g)] for g in range(9)]
    ax[1].plot(range(9),values,'o-',lw=1,ms=4,label=kind,color=color)
ax[1].axhline(0,color='#444',lw=1);ax[1].set_xticks(range(9));ax[1].grid(alpha=.15)
ax[1].set_ylabel('固定源JOINT − 简化监督控制的组均损失（步）');ax[1].set_xlabel('完整来源组编号（每组6，非新评价人口）');ax[1].legend(fontsize=8)
fig.suptitle('旧TRAIN消融：联合关联是否带来超出简化辅助监督的任务区别？',fontsize=14)
fig.text(.5,.012,'原候选固定；仅改变辅助TRAIN标签；全部9组、32原程序＋12新控制。描述性分析，不是独立收益或新颖性证据。',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.05,1,.88))
for ext in ('png','svg'):fig.savefig(out/('supervision_ablation.'+ext),dpi=160)
plt.close(fig);p=out/'supervision_ablation.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text(encoding='utf8').splitlines())+'\n',encoding='utf8',newline='\n')
io.write(out/'plot_receipt.json',dict(integrity='FOR_ACTUAL_VISUAL_REVIEW',result_sha256=io.sha(path.parent/'results.json'),
    artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.suffix in ('.png','.svg')},matplotlib_version=matplotlib.__version__,
    numpy_version=np.__version__,wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0));print(out/'supervision_ablation.png')
