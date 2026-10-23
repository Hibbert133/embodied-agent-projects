"""Scientific figures from closed audited summaries; separate plotting runtime."""
from pathlib import Path
import argparse,json,hashlib,platform
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager,FontProperties
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def main(path):
    out=path.resolve().parent;result=read(out/'results.json');audit=read(out/'audit.json');assert audit['integrity']=='PASSED'
    for n,h in audit['artifact_sha256'].items():assert sha(out/n)==h
    font=Path('C:/Windows/Fonts/msyh.ttc');fontManager.addfont(str(font));plt.rcParams.update({'font.family':FontProperties(fname=str(font)).get_name(),'axes.unicode_minus':False,'font.size':10,'svg.hashsalt':'acquisition-support-v1'})
    dest=out/'figures';dest.mkdir(exist_ok=False)
    def save(fig,name):
        for ext in ('png','svg'):fig.savefig(dest/(name+'.'+ext),dpi=160,bbox_inches='tight')
        plt.close(fig)
    banks=result['banks'];fig,axes=plt.subplots(1,2,figsize=(14,5.6),layout='constrained')
    x=np.arange(3);width=.24
    arrays=[]
    for b in banks:
        cells=b['all_task_context_cells'];arrays.append([np.mean([c['RAW_PI_mean_loss'] for c in cells]),np.mean([c['all_program_clairvoyant_min_mean'] for c in cells]),np.mean([c['best_MOVE_mean_loss'] for c in cells])])
    values=np.asarray(arrays)
    for i,(name,color) in enumerate(zip(('实际 RAW PI(.5s)','全程序事后最小','MOVE 子集事后最小'),('#487a97','#bd793e','#958c63'))):
        bars=axes[0].bar(x+(i-1)*width,values[:,i],width,label=name,color=color);axes[0].bar_label(bars,fmt='%.1f',padding=3)
    axes[0].set_xticks(x,[b['bank']+'\nN='+str(b['units']) for b in banks]);axes[0].set_ylabel('完整截止损失（步，越低越好）');axes[0].legend(loc='upper left',fontsize=9);axes[0].set_ylim(0,float(values.max())*1.42);axes[0].grid(axis='y',alpha=.2)
    for i,b in enumerate(banks):
        v=[g['mean_best_MOVE_minus_RAW_PI'] for g in b['complete_group_room']]
        axes[1].scatter(i+np.linspace(-.13,.13,len(v)),v,color='#958c63',s=35)
        axes[1].scatter([i],[np.mean(v)],marker='D',color='#853f2f',s=60)
    axes[1].axhline(0,color='black',lw=1);axes[1].set_xticks(x,[b['bank'] for b in banks]);axes[1].set_ylabel('MOVE事后最小 − RAW PI（步）\n点为完整组；菱形为组等权均值');axes[1].grid(axis='y',alpha=.2)
    fig.suptitle('已执行程序集合的事后实现空间\n使用未来结局；不是可部署方法、条件期望、总体价值界或独立确认',fontsize=13);save(fig,'portfolio_room')
    entries=[('AFTER8','BEGIN_C8_PI_0.5_NOW','8步后\n立即PI'),('BEFORE_MOVE','BEGIN_C8_PI_0.5_NOW','移动前\n此时才PI'),
        ('BEFORE_MOVE','MOVE_THEN_KEEP_C8_PI_0.5','移动前\n移动+旧C8PI'),('AFTER_MOVE','REJECT_KEEP_C8_PI_0.5_AFTER_MOVE','移动后\n拒绝+旧C8PI'),
        ('AFTER_MOVE','REIDENTIFY_AFTER_MOVE','移动后\n重新辨识'),('AFTER_MOVE','SHORT_VALIDATION_RETURN_OLD','移动后\n短验证返回'),
        ('RAW_PI_BEFORE_MOVE','CONTINUE_RAW_PI_0.5','RAW历史\n继续PI'),('RAW_PI_BEFORE_MOVE','MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY','RAW历史\n移动保留PI')]
    matrix=[];labels=[]
    for b in banks:
        row=[];text=[]
        for stage,request,_ in entries:
            c=next(c for c in b['support_counts'] if (c['stage'],c['requested_suffix'])==(stage,request));n=c['canonical_live_units'];row.append(c['supported_units']/n if n else np.nan)
            text.append(str(c['supported_units'])+'/'+str(n)+'\nN='+str(c['complete_denominator']))
        matrix.append(row);labels.append(text)
    fig,ax=plt.subplots(figsize=(14,4.4),layout='constrained');im=ax.imshow(np.array(matrix),cmap='Blues',vmin=0,vmax=1,aspect='auto')
    ax.set_xticks(range(len(entries)),[e[2] for e in entries]);ax.set_yticks(range(3),[b['bank'] for b in banks])
    for i,row in enumerate(matrix):
        for j,v in enumerate(row):ax.text(j,i,labels[i][j],ha='center',va='center',color='white' if np.isfinite(v) and v>.6 else 'black')
    fig.colorbar(im,ax=ax,label='有支持／规范节点仍存活');ax.set_title('实际匹配后缀的支持\n格内：有支持／规范存活，N为完整单元分母；0是缺失支持，不是零收益',fontsize=13);save(fig,'suffix_support')
    receipt={'integrity':'GENERATED_PENDING_VISUAL_REVIEW','generator_sha256':sha(Path(__file__)),'audit_sha256':sha(out/'audit.json'),
        'output_sha256':{str(p.relative_to(out)):sha(p) for p in dest.iterdir()},'python':platform.python_version(),'numpy':np.__version__,'matplotlib':matplotlib.__version__,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0}
    with (out/'figure_receipt.json').open('x',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
    print('Generated two complete-population descriptive figures',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();main(a.manifest)
