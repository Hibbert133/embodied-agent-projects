from pathlib import Path
import hashlib,json,os,sys
path=Path(sys.argv[1]).resolve();packages=Path(sys.argv[2]).resolve();sys.path.insert(0,str(packages));os.environ['MPLCONFIGDIR']=str(packages.parent/'mpl_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
base=path.parent;result=json.loads((base/'development_results.json').read_text(encoding='utf8'));audit=json.loads((base/'replay_audit.json').read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert audit['integrity']=='PASSED' and audit['results_sha256']==sha(base/'development_results.json')
folder=base/'presentation/figures';folder.mkdir(exist_ok=False)
font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
rows=result['summaries'];labels=['继续0.5','任务均值','静态线性','静态核岭','继续/后线性','继续/后核岭','8步/后线性','8步/后核岭','移动/后线性','移动/后核岭','两阶段线性','两阶段核岭']
assert len(rows)==len(labels)==12
fig,axes=plt.subplots(2,1,figsize=(14,7.5),layout='constrained')
colors=['#737373','#737373','#2d6f98','#2d6f98',*['#51836e']*6,'#9e6a49','#9e6a49']
axes[0].bar(range(12),[r['mean_loss'] for r in rows],color=colors);axes[0].set_ylabel('平均完整截止损失（步）');axes[0].set_ylim(bottom=0)
axes[1].bar(range(12),[100*r['success']/r['units'] for r in rows],color=colors);axes[1].set_ylabel('成功率（%）');axes[1].set_ylim(0,105)
for ax in axes:ax.set_xticks(range(12),labels,rotation=20,ha='right');ax.grid(axis='y',alpha=.15)
fig.suptitle('全部12个标准参考：CAL事实分支开发重放（每项18单元，3个独立组）\n无新增机器人交互；不是独立部署、任务资格或新颖性证据',fontsize=12)
fig.savefig(folder/'all_development_selectors.png',dpi=170);fig.savefig(folder/'all_development_selectors.svg');plt.close(fig)
values=np.array([[r['group_differences_to_CONTINUE_05'][str(g)] for g in range(3)] for r in rows]);limit=max(1.,float(np.max(np.abs(values))))
fig,ax=plt.subplots(figsize=(8,7.6),layout='constrained');im=ax.imshow(values,vmin=-limit,vmax=limit,cmap='RdBu_r',aspect='auto')
for i in range(12):
    for j in range(3):ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center',color='white' if abs(values[i,j])>.6*limit else 'black')
ax.set_yticks(range(12),labels);ax.set_xticks(range(3),['组0 / 16步','组1 / 32步','组2 / 64步']);ax.set_xlabel('每组均含三任务×两条件');fig.colorbar(im,ax=ax,label='完整损失差：参考减继续0.5（步）')
fig.suptitle('全部组差值：负值更好，零表示相同\n每干预时点只有一个独立开发组，不宣称充分功效或稳定优势',fontsize=12)
fig.savefig(folder/'all_group_differences.png',dpi=170);fig.savefig(folder/'all_group_differences.svg');plt.close(fig)
for p in folder.glob('*.svg'):p.write_text('\n'.join(line.rstrip(' \t\r') for line in p.read_text(encoding='utf8').splitlines())+'\n',encoding='utf8',newline='\n')
receipt=dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',script_sha256=sha(Path(__file__)),results_sha256=sha(base/'development_results.json'),
    artifact_sha256={p.name:sha(p) for p in folder.iterdir() if p.suffix in ('.png','.svg')},matplotlib_version=matplotlib.__version__,numpy_version=np.__version__,
    new_physics=0,new_fits=0,online_LLM_API_calls=0,scientific_statistics_recomputed=False)
(folder/'plot_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(dict(integrity=receipt['integrity'],figures=4))
