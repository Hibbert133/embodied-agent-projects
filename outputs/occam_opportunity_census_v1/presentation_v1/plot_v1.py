"""Plot every census unit and every exact gap value; no new estimation."""
from pathlib import Path
from time import perf_counter_ns
import argparse
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/occam_opportunity_census_v1'
EXPECTED = '0214bd46cb101b982de982ca93e75b228cf218d09bad97abf28b490b660c960a'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(packages):
    start = perf_counter_ns()
    sys.path.insert(0, str(packages))
    os.environ['MPLCONFIGDIR'] = str(packages.parent / 'mpl_cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    path = BASE / 'analysis_v1/statistics.json'
    assert sha(path) == EXPECTED
    stats = json.loads(path.read_text(encoding='utf-8'))
    audit = json.loads((path.parent / 'audit.json').read_text(encoding='utf-8'))
    assert audit['integrity'] == 'PASSED_INDEPENDENT_CSV_SCALAR_FRACTION_AUDIT'
    units = stats['units']
    assert len(units) == 54 and stats['post_hoc_descriptive_only'] and not stats['deployable_selector']
    font = Path('C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=font).get_name(),
        'font.size': 11, 'axes.unicode_minus': False, 'svg.fonttype': 'path'})
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={'width_ratios': [1.7, 1]})
    fig.subplots_adjust(left=0.07, right=0.985, top=0.77, bottom=0.23, wspace=0.20)
    ax, hist = axes
    tags = ('PI_0125', 'PI_0500', 'PI_2000', 'PI_8000')
    masks = [all(not u['fixed_programs'][t+'__CONTINUE']['success'] for t in tags) for u in units]
    for kind, color, marker, label in [(0, '#889398', 'o', '无差额'), (1, '#288584', 'o', '有差额，继续臂有成功程序'),
                                       (2, '#b65839', 'D', '有差额，四个继续程序均失败')]:
        selected = [(i+1, u['acquisition_opportunity']) for i, u in enumerate(units)
                    if (2 if masks[i] and u['acquisition_opportunity'] > 0 else 1 if u['acquisition_opportunity'] > 0 else 0) == kind]
        ax.scatter([p[0] for p in selected], [p[1] for p in selected], color=color, marker=marker, s=29, label=label, zorder=3)
    labels = []
    for group in range(9):
        selected = [u for u in units if u['group'] == group]
        assert len(selected) == 6 and len({u['planned_boundary'] for u in selected}) == 1
        labels.append('G'+str(group)+'\nB='+str(selected[0]['planned_boundary']))
        if group:
            ax.axvline(6*group+0.5, color='#d7dddf', linewidth=0.6)
    ax.set(xlim=(0, 55), ylim=(-12, 430), xticks=[3.5+6*g for g in range(9)], xticklabels=labels,
           ylabel='获取记录差额 C − R（步）', xlabel='全部54单元：按组及原任务／条件顺序，未按损失排序')
    ax.axhline(0, color='#889398', linewidth=0.7)
    ax.grid(axis='y', alpha=0.15)
    ax.legend(loc='upper right', frameon=False, fontsize=9)
    bins = stats['exact_severity_frequencies']['acquisition_opportunity']
    assert sum(b['units'] for b in bins) == 54
    bars = hist.bar(range(len(bins)), [b['units'] for b in bins], color=['#889398' if b['difference'] == 0 else '#288584' for b in bins])
    hist.bar_label(bars, padding=3)
    hist.set(xticks=range(len(bins)), xticklabels=[str(b['difference']) for b in bins], ylim=(0, 54),
             xlabel='全部实际差额取值（步）', ylabel='单元数／54', title='47个零差额，7个正差额')
    hist.grid(axis='y', alpha=0.15)
    for axis in axes:
        axis.spines[['top', 'right']].set_visible(False)
    fig.suptitle('固定程序菜单的获取记录差额集中于少数单元', fontsize=16, weight='bold', y=0.965)
    fig.text(0.5, 0.88, '事后描述性分析｜12个已执行固定程序｜9个独立组｜未来结局参与取最小值', ha='center')
    fig.text(0.07, 0.105, 'C：四个继续程序的最低记录损失；R：三种获取臂×四个固定增益的最低记录损失。完整在线成本已包含。', fontsize=10)
    fig.text(0.07, 0.055, '这些差额不证明决策时可预测、不是期望收益上界或纯信息收益；旧接收者和原资格结论保持不变。', fontsize=10)
    out = BASE / 'presentation_v1/figures'
    out.mkdir(exist_ok=False)
    for ext in ('png', 'svg'):
        fig.savefig(out / ('all_54_units.'+ext), dpi=220)
    plt.close(fig)
    assert sha(path) == EXPECTED
    receipt = dict(integrity='PLOTTED_ALL_54_UNITS_AND_ALL_EXACT_GAP_VALUES', statistics_sha256=EXPECTED,
        audit_sha256=sha(path.parent / 'audit.json'), source_sha256=sha(__file__),
        files_sha256={p.name: sha(p) for p in out.iterdir()}, existing_isolated_Matplotlib_reused=True,
        dependencies_installed=0, new_environment_interactions=0, new_model_queries=0, new_fits=0,
        online_LLM_API_calls=0, wall_ns=perf_counter_ns()-start)
    with (out / 'plot_receipt.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(integrity=receipt['integrity'], statistics_sha256=EXPECTED)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--packages', type=Path, required=True)
    main(parser.parse_args().packages.resolve())
