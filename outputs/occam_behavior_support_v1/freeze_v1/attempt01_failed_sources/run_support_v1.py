"""Freeze then read only complete historical TRAIN; never imports scientific code."""
from pathlib import Path
from time import perf_counter_ns
from datetime import datetime, timezone
from contextlib import redirect_stdout, redirect_stderr, contextmanager
from unittest.mock import patch
import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import unittest
import numpy as np
import support_core_v1 as c
import support_audit_v1 as a

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/occam_behavior_support_v1'
TRAIN = ROOT / 'outputs/occam_reference_train_v3/development_v1/occam_reference_train_v3_20261028T071949Z_c92356173d9e'
REPORT = ROOT / 'reports/occam_behavior_support_v1_zh.md'
PROTOCOL = ROOT / 'docs/protocols/occam_behavior_support_v1_zh.md'
FROZEN = BASE / 'freeze_v1/complete.json'
OUT = BASE / 'analysis_v1'
FIXED_INPUTS = {
    'manifest.json': '7416700122909b15ffeda1a3ca2925d325bebe92b1eab00cbe3dfea329e0a413',
    'train/audit.json': 'a4d1a5d8ac1e2357c82ea129b454802e9c376f8777daeccf06a4dae07ee3e5db',
    'train/process_audit.json': '2b77793a50aeab8c008e9d3ffb11dc72261d9694033d2a369eef137546e5e745',
    'train/summary.json': '507d16e3b15d9c7e3e937e4a79c85c05ab3080c762ef484092215bc10b205040',
    'train/completion.json': 'dfad7a4f126c4d21754146d459b80411a7ca907895dee83d29ddc4b6d2249ce6',
    'train/public_trajectories.jsonl.gz': 'f4c5c0a774c6116308feffee18e69739c6f02696a78ed47d540cd103167727e3',
}
PRODUCERS = ('src/analysis/occam_reference_train_io_v3.py', 'src/analysis/occam_reference_train_audit_v3.py',
             'src/analysis/occam_reference_train_collect_v3.py', 'src/probe/occam_training_program_v1.py',
             'src/probe/occam_training_behavior_v1.py', 'src/probe/occam_performance_core_v1.py',
             'src/probe/occam_window_cost_v1.py')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''): h.update(block)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        c.require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def loads(text): return json.loads(text, object_pairs_hook=unique)
def read(path): return loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')


def rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream: yield loads(line)


def emit(stream, value): stream.write(json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n')


def source_inputs():
    result = {str(TRAIN / name): digest for name, digest in FIXED_INPUTS.items()}
    m = read(TRAIN / 'manifest.json')
    result.update({str(ROOT / name): m['source_sha256'][name] for name in PRODUCERS})
    return result


def verify_hashes(bindings):
    for name, digest in bindings.items(): c.require(sha(name) == digest, 'immutable bytes changed ' + name)


def scientific_zero():
    return dict(new_environment_interactions=0, controlled_resets=0, all_resets=0, physical_frames=0,
                policy_queries=0, neural_or_response_training=0, model_predictions=0, filter_updates=0,
                scientific_linear_solves=0, new_episode_allocations=0, online_LLM_API_calls=0)


class Guard:
    def __init__(self, allowed):
        self.allowed = {str(Path(p).resolve()) for p in allowed}
        self.enabled = False
        self.counts = dict(blocked_file_reads=0, blocked_file_writes=0, process_or_network_attempts=0)
        self.open_counts = {}

    def __call__(self, event, args):
        if not self.enabled: return
        if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'socket.connect', 'socket.connect_ex', 'socket.bind', 'socket.getaddrinfo'):
            self.counts['process_or_network_attempts'] += 1
            raise RuntimeError('No process/network in saved-record analysis')
        if event != 'open' or not isinstance(args[0], (str, bytes, os.PathLike)): return
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(x in mode for x in 'wax+')) or (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)))
        inside = path == OUT or OUT in path.parents
        okay = (inside or path == REPORT) if writing else (str(path) in self.allowed or inside or path == REPORT)
        if not okay:
            self.counts['blocked_file_writes' if writing else 'blocked_file_reads'] += 1
            raise RuntimeError('Undeclared file access ' + str(path))
        key = ('write:' if writing else 'read:') + str(path)
        self.open_counts[key] = self.open_counts.get(key, 0) + 1


def freeze():
    folder = FROZEN.parent
    folder.mkdir(exist_ok=False)
    started = perf_counter_ns()
    sources = sorted((BASE/'tools').glob('*.py')) + [BASE/'.gitattributes', PROTOCOL]
    input_hashes = source_inputs(); verify_hashes(input_hashes)
    source_hashes = {str(p): sha(p) for p in sources}
    for p in sources:
        if p.suffix == '.py': compile(p.read_bytes(), str(p), 'exec')
    console = io.StringIO()
    with redirect_stdout(console), redirect_stderr(console):
        suite = unittest.defaultTestLoader.discover(str(BASE/'tools'), pattern='test_support_v1.py')
        result = unittest.TextTestRunner(stream=console, verbosity=2).run(suite)
    (folder/'unit_tests.log').write_text(console.getvalue(), encoding='utf-8', newline='\n')
    c.require(result.wasSuccessful() and result.testsRun == 24, 'formal finite-tree unit checks')
    m, audit, process, summary = [read(TRAIN/p) for p in ('manifest.json', 'train/audit.json', 'train/process_audit.json', 'train/summary.json')]
    c.require(audit['integrity'] == 'PASSED' and process['integrity'] == 'PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY', 'prior two-level audit')
    c.require(audit['public_trajectories_sha256'] == FIXED_INPUTS['train/public_trajectories.jsonl.gz'], 'public projection provenance')
    c.require(summary['executions'] == summary['allocated_executions'] == 648 and summary['unstarted'] == 0 and summary['failure'] is None, 'complete source allocation')
    schedules = []
    for spec in m['config']['populations']['TRAIN']:
        key = [spec['seed'], 2026102863, ('CONTINUE', 'VALIDATE8', 'MOVE_MEASURE').index(spec['acquisition_action'])]
        assigned = np.random.default_rng(np.random.SeedSequence(key)).integers(0,4,31).tolist()
        schedules.append(assigned if spec['behavior'] == 'RANDOM_WINDOW' else [assigned[0]]*31)
    value = dict(integrity='FROZEN_SAVED_TRAIN_ACTION_FACTOR_CHECK_ONLY', created_utc=datetime.now(timezone.utc).isoformat(),
        source_sha256=source_hashes, input_sha256=input_hashes, prior_manifest_id=m['manifest_id'],
        unit_tests=24, compile_files=sum(p.suffix == '.py' for p in sources), tests_log_sha256=sha(folder/'unit_tests.log'),
        allocated_trajectories=648, observed_windows=3296, expected_cells=108, independent_groups=18,
        assigned_schedules=schedules, analysis_cap='two semantic public projection parses plus byte-hash passes; no resampling or outcome fitting',
        assumed_models_are_not_real_propensity_certificates=True, target_policy_value_estimation=False,
        scientific_counters=scientific_zero(), numpy_version=np.__version__, shared_PRNG_implementation_disclosed=True,
        current_qualification_results_used=False, original_comparisons_changed=False, publication_goal_complete=False,
        wall_ns=perf_counter_ns()-started)
    verify_hashes(input_hashes); verify_hashes(source_hashes); write(FROZEN, value)
    return dict(integrity=value['integrity'], unit_tests=value['unit_tests'], freeze_sha256=sha(FROZEN))


def check_frozen():
    plan = read(FROZEN)
    c.require(plan['integrity'] == 'FROZEN_SAVED_TRAIN_ACTION_FACTOR_CHECK_ONLY', 'frozen analysis only')
    verify_hashes(plan['input_sha256']); verify_hashes(plan['source_sha256'])
    c.require(sha(FROZEN.parent/'unit_tests.log') == plan['tests_log_sha256'], 'unit source/receipt binding')
    return plan


def cell_key(spec): return tuple(spec[k] for k in ('task', 'context', 'planned_boundary', 'acquisition_action', 'behavior'))


def analyze(plan):
    started = perf_counter_ns()
    m, audited, compact = [read(TRAIN/p) for p in ('manifest.json','train/audit.json','train/summary.json')]
    specs = m['config']['populations']['TRAIN']; public = rows(TRAIN/'train/public_trajectories.jsonl.gz')
    trajectories, window_count = [], 0
    with (OUT/'trajectories.jsonl').open('x', encoding='utf-8', newline='\n') as tf, (OUT/'windows.jsonl').open('x', encoding='utf-8', newline='\n') as wf:
        for i, spec in enumerate(specs):
            p = next(public)
            c.require(type(p) is dict and set(p) == {'sequence','value'} and p['sequence'] == i, 'exact public row order')
            for key in c.SPEC_KEYS:
                c.require(audited['panels'][i][key] == compact['rows'][i][key] == spec[key], 'source allocation identity')
            row, steps = c.describe_windows(spec, audited['panels'][i], compact['rows'][i], p['value'], plan['assigned_schedules'][i])
            emit(tf, dict(sequence=i, value=row)); trajectories.append(row)
            for step in steps:
                emit(wf, dict(sequence=window_count, case_index=i, value=step)); window_count += 1
    c.require(next(public, None) is None and len(trajectories) == 648 and window_count == 3296, 'all source rows/windows exactly once')
    summary = c.summarize(trajectories); cells = []
    for key in sorted({cell_key(s) for s in specs}):
        subset = [r for r in trajectories if cell_key(r['spec']) == key]
        c.require(len(subset) == 6, 'complete cell denominator')
        cells.append(dict(cell=list(key), summary=c.summarize(subset)))
    c.require(len(cells) == 108 and len(summary['groups']) == 18, 'all cells/groups')
    write(OUT/'statistics.json', dict(overall=summary, cells=cells))
    write(OUT/'analysis_complete.json', dict(integrity='COMPLETE_DESCRIPTIVE_ACTION_FACTOR_RECONSTRUCTION',
        trajectories=len(trajectories), windows=window_count, cells=len(cells), independent_groups=18,
        source_freeze_sha256=sha(FROZEN), artifact_sha256={n:sha(OUT/n) for n in ('trajectories.jsonl','windows.jsonl','statistics.json')},
        scientific_counters=scientific_zero(), wall_ns=perf_counter_ns()-started, task_benefit_claim=False))


def audit(plan):
    started = perf_counter_ns()
    m, compact = [read(TRAIN/p) for p in ('manifest.json','train/summary.json')]
    public, saved, windows = rows(TRAIN/'train/public_trajectories.jsonl.gz'), rows(OUT/'trajectories.jsonl'), rows(OUT/'windows.jsonl')
    trajectories, count = [], 0
    def denied(*args, **kwargs): raise RuntimeError('Main probability/statistics disabled during audit')
    with patch.multiple(c, action_mass=denied, next_probabilities=denied, describe_windows=denied, summarize=denied):
        for i, spec in enumerate(m['config']['populations']['TRAIN']):
            raw, stored = next(public), next(saved)
            a.same(raw['sequence'], i, 'audit source sequence'); a.same(stored['sequence'], i, 'audit output sequence')
            steps = []
            for _ in raw['value']['windows']:
                row = next(windows); a.same(row['sequence'], count, 'audit global window'); a.same(row['case_index'], i, 'audit parent'); count += 1
                steps.append(row['value'])
            a.verify_trajectory(spec, compact['rows'][i], raw['value'], stored['value'], steps)
            trajectories.append(stored['value'])
        a.same(next(public, None), None, 'no omitted source'); a.same(next(saved, None), None, 'no extra trajectory'); a.same(next(windows, None), None, 'no extra window')
        stats = read(OUT/'statistics.json'); a.verify_summary(trajectories, stats['overall'])
        expected = sorted({cell_key(s) for s in m['config']['populations']['TRAIN']})
        a.same([tuple(x['cell']) for x in stats['cells']], expected, 'all cells independently enumerated')
        for cell in stats['cells']:
            subset = [r for r in trajectories if cell_key(r['spec']) == tuple(cell['cell'])]
            a.same(len(subset), 6, 'cell population'); a.verify_summary(subset, cell['summary'])
    a.same(len(trajectories), 648, 'whole population'); a.same(count, 3296, 'whole observed window count')
    complete = read(OUT/'analysis_complete.json')
    for n, h in complete['artifact_sha256'].items(): a.same(sha(OUT/n), h, 'saved result bytes')
    verify_hashes(plan['input_sha256']); verify_hashes(plan['source_sha256'])
    write(OUT/'audit.json', dict(integrity='PASSED_INDEPENDENT_FRACTION_AND_RECORD_RECONSTRUCTION',
        trajectories=len(trajectories), windows=count, cells=108, independent_groups=18, main_probability_and_statistics_disabled=True,
        shared_JSON_and_NumPy_producer_disclosed=True, independent_physics_or_PRNG_implementation=False,
        scientific_counters=scientific_zero(), wall_ns=perf_counter_ns()-started, task_benefit_or_propensity_certificate=False))


def report(plan):
    stats = read(OUT/'statistics.json')['overall']['counts']
    audit_result = read(OUT/'audit.json'); completion = read(OUT/'analysis_complete.json')
    lines = ['# TRAIN 行为支持检查 v1（中文）', '', '**全部新增结果均为事后描述性分析。**', '',
        f"完整来源为 18 组／648 条轨迹、{stats['windows']} 个实际窗口；独立分式和记录核对通过。",
        f"非空 {stats['nonempty']}，边界前结束 {stats['before_intervention']}，获取后无任务窗口 {stats['after_acquisition_no_window']}，短窗口 {stats['short_windows']}。空窗不填零。", '',
        f"实际发生增益变化的轨迹有 {stats['observed_switched_trajectories']} 条；在全部非空轨迹中，统一按每窗 1/4 所得联合因子与假想隐藏混合不同的有 {stats['naive_uniform_joint_mismatch']} 条。",
        '这些是完整人口的事实计数及明确工作模型的代数结果，不是增益变化的任务因果效果。', '',
        '|任务|轨迹／非空|实际窗口|短窗|统一因子不一致轨迹|', '|---|---:|---:|---:|---:|']
    all_rows = [x['value'] for x in rows(OUT/'trajectories.jsonl')]
    for task in ('push-v3','reach-v3','door-open-v3'):
        subset = [r for r in all_rows if r['spec']['task'] == task]
        lines.append(f"|{task}|{len(subset)}／{sum(bool(r['windows']) for r in subset)}|{sum(r['windows'] for r in subset)}|{sum(r['short_windows'] for r in subset)}|{sum(r['naive_uniform_joint_factor_equals_hidden_mixture'] is False for r in subset)}|")
    lines += ['', '完整 108 个分层、18 个组、648 条轨迹和 3,296 个逐窗条目分别保存在 statistics.json、trajectories.jsonl、windows.jsonl；按轨迹→组→组等权汇总。未作任务表现筛选、价值估计、ESS 或置信区间。', '',
        '在工作随机化模型下，R 的动作核乘积为 4^-k；B 首次 1/4、以后保持，因此改变动作序列的 B 因子为零。整段以等概率选 R/B 的隐藏混合因子是 0.5×4^-k + 0.125×I(全相同)，不能在每窗重新混合。两步保持为 5/32，两步改变为 1/32；统一均匀参考均为 1/16。', '',
        '支持证据：原声明的执行前缀与冻结 seed／PRNG 分配一致，全部原标签和缺失保留；分式联合式、前缀比、完整组权重经独立复算。反证／限制：固定 seed 预分配并不自行证明统计外生性；共享 NumPy PRNG 不是独立随机化验证。动作核乘积没有包括状态、观测和停止核，不能称为完整轨迹概率。没有动作时乘积 1 只是约定，逆因子及动作统计保持缺失。', '',
        '隐藏混合还要求在适当信息集条件下行为外生，并且给定相同历史／动作后的转移、观测、停止机制不因行为标签本身改变。这里没有资格证明。全因子获取动作也不是自动每次概率 1/3。配对行为、多个动作和相关窗口不能当独立抽样单位。', '',
        '后续判断：既不能把全部旧标签套到改变动作的接收者，也不能由支持问题断言标准完整 Q／DR 不适用。应另行冻结完整目标程序、行为信息集和序贯概率、支持及停止处理，使用独立数据验证；恒定接收者的实际完整结局可保留为标准监督参考。不能把在本 TRAIN 学到的接收者再用同一 TRAIN 冒充独立离策略校准。', '',
        '当前自身历史资格实验及主比较不变。其结果不用于本检查调参；若不具竞争力，按原停止规则封存本版参考，不围绕它添加门控。混合概率代数、完整风险和事后分层均不是新颖性或 CCF A 证据。', '',
        f"费用：本阶段环境交互／全部重置／物理帧／策略查询／预测／拟合／滤波更新／科学线性求解／新 seed／在线 LLM API 均为 0。分析 {completion['wall_ns']/1e9:.3f} 秒，独立审计 {audit_result['wall_ns']/1e9:.3f} 秒；24 项合成检查另记。",
        '历史来源费用单列：TRAIN 648 次、80,390 控制步、33,048 次全部重置、16,925,950 物理帧；另有来源 NATIVE 36 次、5,399 控制步、1,836 次全部重置、944,995 帧。旧采集费用没有重新发生，也未从总体费用中抹去；标准接收者训练及更早 C8 来源费用沿用其交付清单，非本检查新费用。', '',
        '来源：原 manifest '+plan['prior_manifest_id']+'；公开投影 SHA-256 '+FIXED_INPUTS['train/public_trajectories.jsonl.gz']+'。逐文件来源、实现、协议和回执哈希见 freeze_v1/complete.json 与本阶段 complete.json。', '']
    text = '\n'.join(lines)
    (OUT/'report_zh.md').write_text(text, encoding='utf-8', newline='\n')
    with REPORT.open('x', encoding='utf-8', newline='\n') as f: f.write(text)


def run():
    plan = check_frozen(); OUT.mkdir(exist_ok=False)
    # Finish lazy runtime initialization before restricting scientific file reads.
    np.random.default_rng(np.random.SeedSequence([0])).integers(0,4,1)
    guard = Guard([FROZEN, FROZEN.parent/'unit_tests.log', *plan['input_sha256'], *plan['source_sha256']])
    sys.addaudithook(guard); guard.enabled = True
    started = perf_counter_ns()
    try:
        write(OUT/'intent.json', dict(freeze_sha256=sha(FROZEN), scientific_counters=scientific_zero()))
        analyze(plan); audit(plan); report(plan)
        verify_hashes(plan['input_sha256']); verify_hashes(plan['source_sha256'])
        write(OUT/'guard.json', dict(counts=guard.counts, file_opens=guard.open_counts, declared_input_files_only=True))
        c.require(not any(guard.counts.values()), 'zero forbidden attempts')
        artifacts = sorted(p for p in OUT.iterdir() if p.is_file()) + [REPORT]
        write(OUT/'complete.json', dict(integrity='PASSED_COMPLETE_DESCRIPTIVE_TRAIN_SUPPORT_AUDIT',
            artifact_sha256={str(p.relative_to(ROOT)):sha(p) for p in artifacts},
            source_freeze_sha256=sha(FROZEN), scientific_counters=scientific_zero(),
            current_qualification_results_used=False, task_benefit_or_novelty_claim=False,
            wall_ns=perf_counter_ns()-started, publication_goal_complete=False))
    except BaseException as error:
        write(OUT/'FAILED_ATTEMPT_RETAINED.json', dict(type=type(error).__name__, message=str(error), scientific_counters=scientific_zero(), guard=guard.counts))
        raise
    finally:
        guard.enabled = False
    return dict(integrity=read(OUT/'complete.json')['integrity'], trajectories=648, windows=3296)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=('freeze','run'))
    args = parser.parse_args(); print(json.dumps(freeze() if args.command == 'freeze' else run(), ensure_ascii=False))
