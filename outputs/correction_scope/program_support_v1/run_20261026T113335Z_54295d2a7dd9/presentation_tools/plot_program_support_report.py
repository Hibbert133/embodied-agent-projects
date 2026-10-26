from pathlib import Path
import hashlib,json,os,sys
path=Path(sys.argv[1]).resolve();packages=Path(sys.argv[2]).resolve();sys.path.insert(0,str(packages))
os.environ['MPLCONFIGDIR']=str(packages.parent/'mpl_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
base=path.parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=json.loads((base/'results.json').read_text(encoding='utf8'));audit=json.loads((base/'audit.json').read_text(encoding='utf8'))
assert audit['integrity']=='PASSED' and audit['results_sha256']==sha(base/'results.json')
out=base/'presentation/figures';out.mkdir(exist_ok=False);font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
fig,axes=plt.subplots(2,1,figsize=(13.5,8),layout='constrained',gridspec_kw={'height_ratios':[1,1.4]})
p=result['programs'];labels=[('继续','普通8步','移动测量')[r['index']//4]+'\nτ='+str(r['rate']) for r in p]
axes[0].bar(range(12),[r['mean_loss'] for r in p],color=['#367a9b']*4+['#538e74']*4+['#a86a43']*4)
axes[0].set_xticks(range(12),labels);axes[0].set_ylabel('平均完整截止损失（步）');axes[0].set_ylim(bottom=0)
axes[0].set_title('全部12个已执行固定程序（各54单元）；不是训练或独立部署新结果');axes[0].grid(axis='y',alpha=.15)
panels={(p['task'],p['context'],p['boundary']):p['summary']['means']['F_minus_P'] for p in result['panels']}
values=np.array([[panels[t,c,b] for b in (16,32,64)] for t in ('push-v3','reach-v3','door-open-v3') for c in ('UNCHANGED','CHANGED')])
limit=max(1.,float(np.max(np.abs(values))));im=axes[1].imshow(values,aspect='auto',vmin=-limit,vmax=limit,cmap='RdBu')
for i in range(6):
    for j in range(3):axes[1].text(j,i,f'{values[i,j]:.2f}',ha='center',va='center',color='white' if abs(values[i,j])>.6*limit else 'black')
axes[1].set_yticks(range(6),[t+'/'+('不变' if c=='UNCHANGED' else '变化') for t in ('push-v3','reach-v3','door-open-v3') for c in ('UNCHANGED','CHANGED')])
axes[1].set_xticks(range(3),['16步','32步','64步']);axes[1].set_title('全部任务×条件×时点：免费家族事后最小F − 付费家族事后最小P\n正值表示付费叶较好；每格3单元，保留所有负值与提前结束')
fig.colorbar(im,ax=axes[1],label='F−P（步），正值付费事后较好')
fig.suptitle('TRAIN完整事实支持空间：9组54单元648叶\n事后描述性包络，不是可实现策略、信息价值或总体期望界',fontsize=12)
fig.savefig(out/'factual_support.png',dpi=170);fig.savefig(out/'factual_support.svg');plt.close(fig)
p=out/'factual_support.svg';p.write_text('\n'.join(s.rstrip(' \t\r') for s in p.read_text(encoding='utf8').splitlines())+'\n',encoding='utf8',newline='\n')
(out/'plot_receipt.json').write_text(json.dumps(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',script_sha256=sha(Path(__file__)),
    results_sha256=sha(base/'results.json'),artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.suffix in ('.png','.svg')},
    matplotlib_version=matplotlib.__version__,numpy_version=np.__version__,new_physics=0,new_model_fits=0,online_LLM_API_calls=0),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',artifacts=2))
