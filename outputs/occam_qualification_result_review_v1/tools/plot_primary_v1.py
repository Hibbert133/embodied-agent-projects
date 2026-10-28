"""Presentation only: all ten frozen contrasts, without scientific imports."""
from pathlib import Path
from fractions import Fraction
from time import perf_counter_ns
import argparse
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'
OUT = ROOT / 'outputs/occam_qualification_result_review_v1/figures_v1'
EXPECTED = 'dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc'


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
    stats_path = RUN / 'statistics_v1/statistics.json'
    audit_path = RUN / 'statistics_v1/independent_audit.json'
    assert sha(stats_path) == EXPECTED
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    assert audit['integrity'] == 'PASSED' and audit['source_statistics_sha256'] == EXPECTED
    stats = json.loads(stats_path.read_text(encoding='utf-8'))
    rows = stats['primary']
    assert len(rows) == 10 and not stats['task_qualified']
    assert all(r['left'] == 'META_ADAPT__CONTINUE' and r['denominator'] == 54 and r['independent_groups'] == 9 for r in rows)
    assert all((Fraction(r['CI95_exact'][1]) < 0) == r['upper_strictly_below_zero'] for r in rows)
    font = Path('C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=font).get_name(),
                         'font.size': 11, 'axes.unicode_minus': False, 'svg.fonttype': 'path'})
    labels = ['同前缀 T=0.125 秒', '同前缀 T=0.5 秒', '同前缀 T=2 秒', '同前缀 T=8 秒',
              '从重置起 T=0.125 秒', '从重置起 T=2 秒', '从重置起 T=8 秒',
              'ERM_ADAPT__CONTINUE', 'DIRECT_C8', 'MOVE_INTEGRAL']
    fig, (ax, table) = plt.subplots(1, 2, figsize=(16, 8), gridspec_kw={'width_ratios': [1.8, 1.3]})
    fig.subplots_adjust(left=0.20, right=0.99, top=0.82, bottom=0.19, wspace=0.07)
    for i, r in enumerate(rows):
        delta = r['mean_loss_difference']
        lo, hi = r['CI95']
        color = '#257777' if r['upper_strictly_below_zero'] else '#ad691f'
        ax.errorbar(delta, i, xerr=[[delta-lo], [hi-delta]], fmt='o', color=color,
                    markersize=6, capsize=4, linewidth=1.8, zorder=3)
        table.text(0.02, i, f'{delta:+.3f}  [{lo:+.3f}, {hi:+.3f}]', color=color, va='center')
        table.text(0.85, i, '满足' if r['upper_strictly_below_zero'] else '未满足', color=color, va='center')
    ax.axvline(0, color='#5a5a5a', linestyle='--', linewidth=1)
    ax.set(xlim=(-133, 23), ylim=(9.6, -0.8), yticks=range(10), yticklabels=labels,
           xlabel='平均截止损失差（步）：META − 对照；负值更低')
    ax.grid(axis='x', alpha=0.16)
    ax.spines[['top', 'right']].set_visible(False)
    table.set(xlim=(0, 1.05), ylim=ax.get_ylim())
    table.axis('off')
    table.text(0.02, -0.65, '损失差及 95% 区间', weight='bold')
    table.text(0.85, -0.65, '上界 < 0', weight='bold')
    fig.suptitle('完整任务收益资格：十项主比较中三项未满足', y=0.965, fontsize=18, weight='bold')
    fig.text(0.5, 0.90, '全部冻结主比较｜每程序 54 次执行、9 个独立组｜10,000 次整组分层 bootstrap', ha='center')
    fig.text(0.20, 0.10, '资格要求十项区间上界均小于 0；当前未通过。跨零不等于证明方法更差。', fontsize=11)
    fig.text(0.20, 0.055, '“同前缀”先以 T=0.5 秒运行至边界，再切换；“从重置起”全程固定。完整截止损失已含获取成本。', fontsize=10)
    OUT.mkdir(parents=True, exist_ok=False)
    for suffix in ('png', 'svg'):
        fig.savefig(OUT / ('all_ten_primary.' + suffix), dpi=240)
    plt.close(fig)
    assert sha(stats_path) == EXPECTED
    receipt = dict(integrity='GENERATED_ALL_TEN_FROZEN_PRIMARY_COMPARISONS',
                   statistics_sha256=EXPECTED, independent_statistics_audit_sha256=sha(audit_path),
                   manifest_id=stats['manifest_id'], source_scientific_commit='7abaec83b0854f099d6f13f308cc8cd552f50e2b',
                   reader_source_sha256=sha(__file__), matplotlib_version=matplotlib.__version__,
                   reused_existing_isolated_plotting_runtime=True, dependencies_installed=0,
                   project_environment_modified=False, no_scientific_recomputation=True,
                   files_sha256={p.name: sha(p) for p in OUT.iterdir()}, wall_ns=perf_counter_ns()-start,
                   new_environment_interactions=0, new_model_fits=0, online_LLM_API_calls=0)
    with (OUT / 'plot_receipt.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(dict(integrity=receipt['integrity'], output=str(OUT))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--packages', type=Path, required=True)
    main(parser.parse_args().packages.resolve())
