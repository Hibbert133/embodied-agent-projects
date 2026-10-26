from pathlib import Path
import hashlib,json,os,sys
path=Path(sys.argv[1]).resolve();packages=Path(sys.argv[2]).resolve();sys.path.insert(0,str(packages));os.environ['MPLCONFIGDIR']=str(packages.parent/'mpl_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
base=path.parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();audit=json.loads((base/'audit.json').read_text(encoding='utf8'))
assert audit['integrity']=='PASSED' and audit['records_sha256']==sha(base/'constructed_records.jsonl')
rows=[json.loads(line) for line in (base/'constructed_records.jsonl').read_text(encoding='utf8').splitlines()]
chosen=[r for r in rows if r['command']==[.25,-.25,0.,1.] and r['noise_xyz']==[0.,0.,0.]];assert len(chosen)==15
examples=json.loads((base/'construction.json').read_text(encoding='utf8'))['adoption_counterexample']
out=base/'presentation/figures';out.mkdir(exist_ok=False);font_manager.findfont('Microsoft YaHei',fallback_to_default=False)
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
fig,axes=plt.subplots(1,3,figsize=(15,4.4),layout='constrained')
state=sorted([r for r in chosen if r['kind']=='SMOOTH_STATE'],key=lambda r:r['position'])
axes[0].plot([r['position'] for r in state],[r['actual']['state_weight_oracle'] for r in state],'o-',color='#397a9b')
axes[0].set_xlabel('构造坐标 x（非真实工作空间）');axes[0].set_ylabel('评价端权重 w（不供Agent使用）');axes[0].set_title('状态相关混合权：5个审计点')
for kind,label,color in (('FLAT_LEFT','固定左端点','#777777'),('FLAT_RIGHT','固定右端点','#538e74'),('SMOOTH_STATE','状态相关','#bb7849')):
    rr=sorted([r for r in chosen if r['kind']==kind],key=lambda r:r['position'])
    axes[1].plot([r['position'] for r in rr],[r['actual']['executed_action_oracle'][0] for r in rr],'o-',label=label,color=color)
axes[1].set_xlabel('构造坐标 x');axes[1].set_ylabel('施加动作 X（非米/任务损失）');axes[1].set_title('同一命令/零噪声的数值响应');axes[1].legend(fontsize=9)
x=np.arange(2);axes[2].bar(x-.18,[abs(r['initial_prediction_error']) for r in examples],width=.36,label='初始',color='#397a9b')
axes[2].bar(x+.18,[abs(r['next_prediction_error']) for r in examples],width=.36,label='假定下一步',color='#bb7849')
axes[2].set_xticks(x,['小命令 .01','大命令 .5']);axes[2].set_ylabel('固定左模型绝对误差（动作单位）');axes[2].set_title('仅假定 x_next=x+applied_x');axes[2].legend(fontsize=9)
for ax in axes:ax.grid(axis='y',alpha=.15)
fig.suptitle('纯数值构造：非MetaWorld轨迹，无任务成败或安全结论\n标记为审计点，连线仅帮助阅读；当前预测准确不代表后继仍适用',fontsize=12)
fig.savefig(out/'operator_and_example.png',dpi=170);fig.savefig(out/'operator_and_example.svg');plt.close(fig)
p=out/'operator_and_example.svg';p.write_text('\n'.join(line.rstrip(' \t\r') for line in p.read_text(encoding='utf8').splitlines())+'\n',encoding='utf8',newline='\n')
(out/'plot_receipt.json').write_text(json.dumps(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',script_sha256=sha(Path(__file__)),
    records_sha256=sha(base/'constructed_records.jsonl'),audit_sha256=sha(base/'audit.json'),actual_audited_rows_plotted=15,
    no_additional_operator_or_model_queries=True,artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.suffix in ('.png','.svg')},
    matplotlib_version=matplotlib.__version__,numpy_version=np.__version__,new_physics=0,new_model_fits=0,online_LLM_API_calls=0),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(dict(integrity='GENERATED_FOR_ACTUAL_VISUAL_REVIEW',artifacts=2))
