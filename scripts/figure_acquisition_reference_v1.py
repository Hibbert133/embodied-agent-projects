"""Static all-program QUAL figure; stdlib file verification avoids runtime fitting."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import argparse,hashlib,json,socket,sys
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(path):
    start=perf_counter_ns();path=path.resolve();out=path.parent;m=read(path);audit=read(out/'qual/statistics_audit.json')
    assert audit['integrity']=='PASSED' and audit['source_statistics_sha256']==sha(out/'qual/statistics.json')
    for n,h in {**m['source_sha256'],**m['model_input_sha256']}.items():assert sha(ROOT/n)==h,n
    r=read(out/'qual/statistics.json');data=r['program_summaries']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    font=Path('C:/Windows/Fonts/msyh.ttc');assert font.exists();fm.fontManager.addfont(str(font));plt.rcParams['font.family']=fm.FontProperties(fname=str(font)).get_name();plt.rcParams['axes.unicode_minus']=False
    labels=['RAW PI继续','初始C8','原移动积分','固定PD保持','固定PID保持','附近PD保持','附近PID保持','参考+清零','参考+保留','参考清零不探测']
    fig,axes=plt.subplots(2,1,figsize=(15,9),constrained_layout=True)
    axes[0].bar(range(10),[v['mean_deadline_loss'] for v in data],color=['#9ca3af']*7+['#2458a6','#9ca3af','#9ca3af']);axes[0].set_ylim(0,530);axes[0].set_ylabel('平均完整截止损失（步）')
    for i,v in enumerate(data):axes[0].text(i,v['mean_deadline_loss']+5,f'{v["mean_deadline_loss"]:.2f}\n{v["successes"]}/54',ha='center',fontsize=9)
    for i,v in enumerate(data):
        if i in (0,1,2,9):axes[1].text(i,.05,'未测量',ha='center',color='#555555')
        else:axes[1].bar(i,v['complete_windows']/54,color='#2458a6');axes[1].text(i,v['complete_windows']/54+.025,f'{v["complete_windows"]}/54',ha='center',fontsize=9)
    axes[1].set_ylim(0,1.12);axes[1].set_ylabel('全部分配中的完整窗口比例')
    for ax in axes:ax.set_xticks(range(10),labels,rotation=18);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('独立标准参考资格：全部10程序与完整分母\n获取/采用分支门不等于获取前净收益、物理辨识或新算法资格；来源9个独立组。',fontsize=13)
    folder=out/'figures';folder.mkdir(exist_ok=False);fig.savefig(folder/'all_programs.png',dpi=150);fig.savefig(folder/'all_programs.svg');plt.close(fig)
    value={'integrity':'GENERATED_REQUIRES_VISUAL_REVIEW','all_programs':10,'source_statistics_sha256':sha(out/'qual/statistics.json'),'source_statistics_audit_sha256':sha(out/'qual/statistics_audit.json'),
        'generator_sha256':sha(Path(__file__)),'matplotlib':matplotlib.__version__,'python':sys.version,'font':str(font),'wall_ns':perf_counter_ns()-start,
        'output_sha256':{p.relative_to(out).as_posix():sha(p) for p in folder.iterdir()},'new_environment_steps':0,'new_response_training':0,'new_online_LLM_API_calls':0}
    with (out/'figure_receipt.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
    print({'all_programs':10,'figure_directory':str(folder)},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();network={'attempted_calls':0}
    def denied(*args,**kw):network['attempted_calls']+=1;raise RuntimeError('No network in static figure')
    with ExitStack() as stack:
        for obj,name in ((socket.socket,'connect'),(socket.socket,'connect_ex'),(socket,'create_connection')):stack.enter_context(patch.object(obj,name,denied))
        main(v.manifest)
    with (v.manifest.parent/'figure_network_guard.json').open('x',encoding='utf-8') as f:json.dump({'integrity':'PASSED','network':network,'new_online_LLM_API_calls':0},f,indent=2);f.write('\n')
