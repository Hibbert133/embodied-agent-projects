"""Static Chinese scientific figure using the separate plotting runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def plot(path,phase):
    manifest=read(path);root=path.parent/(phase.lower()+'_analysis_v1');saved=read(root/'statistics.json');audit=read(path.parent/(phase.lower()+'_statistics_audit.json'))
    if audit['integrity']!='PASSED' or audit['statistics_sha256']!=sha(root/'statistics.json'):raise ValueError('matching numeric audit required')
    s=saved['statistics'];out=root/'figures';out.mkdir();font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':font.get_name(),'font.size':13,'axes.unicode_minus':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,2,figsize=(15,6),layout='constrained');a,b=axes
    arms=('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP');labels=('直接复用','补测保留','严格更新','稳健更新')
    values=[s['methods'][p]['mean_deadline_loss'] for p in arms]
    if all(v is not None for v in values):
        bars=a.bar(labels,values,color=['#6C7A89','#E9A23B','#789AB9','#3A9C82'],width=.65)
        for bar,p in zip(bars,arms):
            cell=s['methods'][p];a.text(bar.get_x()+bar.get_width()/2,bar.get_height()+3,f"{cell['mean_deadline_loss']:.1f}\n成功 {cell['successes']}/{cell['cases']}",ha='center',va='bottom',fontsize=11)
        a.set_ylim(0,max(1.3*max(values),20))
    else:a.text(.5,.5,'无合格暖状态',transform=a.transAxes,ha='center')
    a.set_ylabel('平均截止损失 / 逻辑步（越低越好）');a.set_title('同一来源状态，四种实际续跑程序')
    nested=s['nested'];bootstrap=s['stream_bootstrap']
    if nested:
        means=np.asarray(nested['mean_contrast'])[:3];positions=np.arange(3)
        b.axvline(0,color='#8A929B',linewidth=1)
        b.scatter(means,positions,color=['#3A9C82','#E9A23B','#789AB9'],s=85,zorder=3)
        if bootstrap and bootstrap['percentile_95'] is not None:
            intervals=np.asarray(bootstrap['percentile_95'])[:3]
            for k,(lo,hi) in enumerate(intervals):b.plot([lo,hi],[k,k],color='#536273',linewidth=2,zorder=2)
        for k,value in enumerate(means):b.annotate(f'{value:+.2f}',(value,k),xytext=(0,13),textcoords='offset points',ha='center')
        b.set_yticks(positions,['总效应：复用 − 稳健更新','动作与费用：复用 − 补测保留','参数更新：补测保留 − 稳健更新']);b.invert_yaxis();b.margins(y=.4)
        b.set_xlabel('截止损失差 / 步（正值表示右侧程序较好）')
        b.set_title('逐未来：总效应 = 动作与费用 + 参数更新')
    else:b.text(.5,.5,'合格状态少于2，统计不适用',transform=b.transAxes,ha='center');b.set_axis_off()
    tag='机械预检，不作主实验推断' if phase=='SMOKE' else '36个完整来源流；区间按九因素格分层重抽'
    fig.suptitle(f"补测动作与参数更新的任务效应：{s['contexts']}个暖状态 × {s['fresh_futures_per_context']}个新未来\n{tag}",fontsize=17)
    fig.savefig(out/'effects.png',dpi=220);fig.savefig(out/'effects.svg');plt.close(fig)
    receipt={k:manifest[k] for k in ('experiment_run_id','manifest_id','source_git_commit')}
    receipt.update(phase=phase,statistics_sha256=sha(root/'statistics.json'),numeric_audit_sha256=sha(path.parent/(phase.lower()+'_statistics_audit.json')),
        python=sys.version,matplotlib=matplotlib.__version__,numpy=np.__version__,font_path=str(Path('C:/Windows/Fonts/msyh.ttc')),
        font_sha256=sha(Path('C:/Windows/Fonts/msyh.ttc')),artifact_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    with (out/'receipt.json').open('x',encoding='utf-8',newline='\n') as handle:json.dump(receipt,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n')
    print(out/'effects.png',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--phase',choices=['SMOKE','MAIN'],required=True);args=parser.parse_args();plot(args.manifest.resolve(),args.phase)
