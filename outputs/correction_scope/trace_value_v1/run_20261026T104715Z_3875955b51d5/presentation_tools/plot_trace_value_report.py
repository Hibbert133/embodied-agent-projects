from pathlib import Path
import hashlib,json,os,sys
path=Path(sys.argv[1]).resolve();packages=Path(sys.argv[2]).resolve();sys.path.insert(0,str(packages));os.environ['MPLCONFIGDIR']=str(packages.parent/'mpl_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
base=path.parent;result=json.loads((base/'results.json').read_text(encoding='utf8'));audit=json.loads((base/'replay_audit.json').read_text(encoding='utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert audit['integrity']=='PASSED' and audit['results_sha256']==sha(base/'results.json')
out=base/'presentation/figures';out.mkdir(exist_ok=False);font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
labels=['继续0.5','移动0.5','免费历史/线性','免费历史/核岭','正常8步/线性','正常8步/核岭','移动全轨迹/线性','移动全轨迹/核岭','移动屏蔽/线性','移动屏蔽/核岭']
rows=result['summaries'];assert len(rows)==10
fig,axes=plt.subplots(2,1,figsize=(14,7.3),layout='constrained');colors=['#777777']*2+['#2b7396']*4+['#4c826c']*2+['#aa7048']*2
axes[0].bar(range(10),[r['mean_loss'] for r in rows],color=colors);axes[0].set_ylabel('平均完整截止损失（步）');axes[0].set_ylim(bottom=0)
axes[1].bar(range(10),[100*r['success']/r['units'] for r in rows],color=colors);axes[1].set_ylabel('成功率（%）');axes[1].set_ylim(0,105)
for ax in axes:ax.set_xticks(range(10),labels,rotation=15,ha='right');ax.grid(axis='y',alpha=.15)
fig.suptitle('全部10参考：TRAIN内按组交叉开发（每项54单元）\n无新增环境交互；训练集重叠，不是独立最终部署或创新证据',fontsize=12)
fig.savefig(out/'all_selectors.png',dpi=170);fig.savefig(out/'all_selectors.svg');plt.close(fig)
contrasts=result['FULL_MASK_contrasts'];values=np.array([[c['group_differences'][str(g)] for g in range(9)] for c in contrasts]);limit=max(1.,float(np.max(np.abs(values))))
fig,ax=plt.subplots(figsize=(12,3.4),layout='constrained');image=ax.imshow(values,vmin=-limit,vmax=limit,cmap='RdBu_r',aspect='auto')
for i in range(2):
    for j in range(9):ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center',color='white' if abs(values[i,j])>.6*limit else 'black')
ax.set_yticks(range(2),[c['kind'] for c in contrasts]);ax.set_xticks(range(9),[f'组{g}\n{(16,32,64)[g%3]}步' for g in range(9)]);fig.colorbar(image,ax=ax,label='FULL−MASK完整损失（步）')
fig.suptitle('同接收者、同真实返回：额外轨迹的组差\n负值较好，零表示相同；交叉训练重叠，不作名义置信区间',fontsize=12)
fig.savefig(out/'FULL_MASK_groups.png',dpi=170);fig.savefig(out/'FULL_MASK_groups.svg');plt.close(fig)
tasks=('push-v3','reach-v3','door-open-v3');contexts=('UNCHANGED','CHANGED');fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
all_values=[p['mean_difference'] for c in contrasts for p in c['panels']];limit=max(1.,max(abs(v) for v in all_values))
for ax,c in zip(axes,contrasts):
    ps={(p['task'],p['context'],p['boundary']):p for p in c['panels']};values=np.array([[ps[(t,k,b)]['mean_difference'] for b in (16,32,64)] for t in tasks for k in contexts]);im=ax.imshow(values,vmin=-limit,vmax=limit,cmap='RdBu_r',aspect='auto')
    for i in range(6):
        for j in range(3):ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center',color='white' if abs(values[i,j])>.6*limit else 'black')
    ax.set_title(c['kind']);ax.set_xticks(range(3),['16步','32步','64步']);ax.set_yticks(range(6),[t+'/'+('不变' if k=='UNCHANGED' else '变化') for t in tasks for k in contexts])
fig.colorbar(im,ax=axes,label='FULL−MASK完整损失（步）');fig.suptitle('全部任务×条件×时点（每格3来源单元）\n仅屏蔽MOVE额外轨迹，返回状态、前缀与花费时钟保留',fontsize=12)
fig.savefig(out/'all_panels.png',dpi=170);fig.savefig(out/'all_panels.svg');plt.close(fig)
for p in out.glob('*.svg'):p.write_text('\n'.join(line.rstrip(' \t\r') for line in p.read_text(encoding='utf8').splitlines())+'\n',encoding='utf8',newline='\n')
(out/'plot_receipt.json').write_text(json.dumps(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',script_sha256=sha(Path(__file__)),results_sha256=sha(base/'results.json'),
    artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.suffix in ('.png','.svg')},matplotlib_version=matplotlib.__version__,numpy_version=np.__version__,
    new_physics=0,new_fits=0,online_LLM_API_calls=0),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',figures=6))
