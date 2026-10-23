"""All fixed programs and paired primary outcomes; presentation only."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import memory_reset_io_v1 as a
io=a.io


def plot(path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    path=Path(path).resolve();a.checked(path);root=path.parent
    result=io.read(root/'qual/statistics.json');out=root/'figures';out.mkdir(exist_ok=False)
    rows=result['program_summaries'];names=[v['program'].replace('LOCAL_PID_','L_') for v in rows]
    fig,axes=plt.subplots(1,2,figsize=(15,7));y=list(range(len(rows)))
    axes[0].barh(y,[v['mean_deadline_loss'] for v in rows],color='#2b6688');axes[0].set_yticks(y,names);axes[0].invert_yaxis();axes[0].set_xlabel('Full deadline loss (lower is better)')
    axes[1].barh(y,[v['successes']/54 for v in rows],color='#3e8a6d');axes[1].set_yticks(y,names);axes[1].invert_yaxis();axes[1].set_xlim(0,1.05);axes[1].set_xlabel('Task success / all 54 assignments')
    fig.suptitle('Standard memory-reset qualification: 9 independent groups, all programs');fig.tight_layout();fig.savefig(out/'full_programs.png',dpi=160);plt.close(fig)
    io.write(out/'plot_receipt.json',dict(integrity='GENERATED_ALL_TEN_PROGRAMS',statistics_sha256=io.sha(root/'qual/statistics.json'),
        files_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args();print(plot(v.manifest))
