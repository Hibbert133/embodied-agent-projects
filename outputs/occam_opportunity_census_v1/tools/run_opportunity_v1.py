"""Versioned record-only entry; freeze before one actual descriptive census."""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import traceback
import opportunity_core_v1 as core
import opportunity_audit_v1 as independent

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/occam_opportunity_census_v1'
OUT = BASE / 'analysis_v1'
FREEZE = BASE / 'freeze_v1/complete.json'
RUN = ROOT / 'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'
MID = '19347fbe7b039fabd536c411d74e87a823bd0925cd2bee9e5705329cdb77f78d'
STAT = 'dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc'
DOCS = ('docs/protocols/occam_opportunity_census_v1_zh.md',
        'docs/research/correction_scope_contribution_review_v10_zh.md',
        'docs/research/correction_scope_candidate_register_v10_zh.md')
IO = dict(JSON_documents=0, JSON_bytes=0, CSV_documents=0, CSV_rows=0, CSV_bytes=0, SHA256_file_passes=0, SHA256_bytes=0)


def sha(path):
    data = Path(path).read_bytes()
    IO['SHA256_file_passes'] += 1
    IO['SHA256_bytes'] += len(data)
    return hashlib.sha256(data).hexdigest()


def read(path):
    data = Path(path).read_bytes()
    IO['JSON_documents'] += 1
    IO['JSON_bytes'] += len(data)
    return json.loads(data.decode('utf-8'))


def csv_read(name):
    path = RUN / 'report_v1' / name
    data = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'), newline='')))
    IO['CSV_documents'] += 1
    IO['CSV_rows'] += len(rows)
    IO['CSV_bytes'] += len(data)
    return rows


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def git(*args):
    return subprocess.check_output(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', *args], cwd=ROOT)


def verify(mapping):
    for name, expected in mapping.items():
        core.require(sha(ROOT / name) == expected, 'source SHA: ' + name)


def source_paths():
    return [*sorted((BASE / 'tools').glob('*.py')), *(ROOT / n for n in DOCS), BASE / '.gitattributes']


def inputs():
    paths = [RUN / n for n in ('manifest.json', 'report_v1/complete.json', 'report_v1/source_manifest.json',
        'report_v1/all_1740_allocated_cases.csv', 'report_v1/all_1566_qualified_cases.csv', 'report_v1/all_29_programs.csv',
        'report_v1/all_522_task_condition_boundary_cells.csv', 'report_v1/all_complete_task_failures.csv',
        'report_v1/all_unresolved_or_unstarted_cases.csv', 'statistics_v1/statistics.json', 'statistics_v1/independent_audit.json',
        'native/process_audit.json', 'native/audit.json', 'qual/process_audit.json', 'qual/audit.json', 'pipeline_v1/complete.json')]
    paths += [ROOT / n for n in ('reports/occam_reference_qualification_v1_zh.md',
        'outputs/occam_qualification_result_review_v1/review_v1/receiver_closure.json')]
    return paths


@contextmanager
def record_only(destination):
    target = Path(destination).resolve()
    counts = dict(scientific_import_attempts=0, network_or_process_attempts=0, outside_output_write_attempts=0)
    forbidden_modules = ('mujoco', 'metaworld', 'gym', 'gymnasium', 'torch', 'src.probe', 'src.rollout')
    core.require(not any(n == p or n.startswith(p+'.') for n in sys.modules for p in forbidden_modules), 'no preloaded science modules')
    active = [True]
    def hook(event, args):
        if not active[0]:
            return
        if event == 'import' and any(args[0] == p or args[0].startswith(p+'.') for p in forbidden_modules):
            counts['scientific_import_attempts'] += 1
            raise RuntimeError('record-only entry forbids scientific imports')
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
            counts['network_or_process_attempts'] += 1
            raise RuntimeError('record-only entry forbids network and child processes')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            mode, flags = args[1], args[2]
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            if writing:
                path = Path(os.fsdecode(args[0])).resolve()
                if path != target and target not in path.parents:
                    counts['outside_output_write_attempts'] += 1
                    raise RuntimeError('record-only entry forbids source writes')
    sys.addaudithook(hook)
    try:
        yield counts
    finally:
        active[0] = False


def admit():
    f = read(FREEZE)
    core.require(f['integrity'] == 'FROZEN_RECORD_ONLY_OPPORTUNITY_CENSUS_V1', 'frozen tested tool')
    verify(f['source_sha256'])
    verify(f['input_sha256'])
    for name, digest in f['source_sha256'].items():
        core.require(hashlib.sha256(git('show', 'HEAD:'+name)).hexdigest() == digest, 'tested source committed before data '+name)
    core.require(git('show', 'HEAD:'+FREEZE.relative_to(ROOT).as_posix()) == FREEZE.read_bytes(), 'freeze receipt committed')
    core.require(not git('status', '--porcelain', '--untracked-files=no').strip(), 'clean frozen tracked state')
    report = read(RUN / 'report_v1/complete.json')
    core.require(report['manifest_id'] == MID and report['allocated'] == 1740 and report['complete_task_failures'] == 99
                 and report['unresolved'] == 0 and report['scientific_population_complete'] and not report['task_qualification'], 'complete negative source only')
    core.require(sha(RUN / 'statistics_v1/statistics.json') == STAT, 'original ten comparisons unchanged')
    return f


def write_csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def report(result):
    means = result['overall']['equal_group_mean_exact']
    fmt = lambda s: format(float(Fraction(s)), '.3f')
    anchors = '\n'.join('|'+t+'|'+fmt(means['baseline_'+t])+'|'+fmt(means['gain_'+t])+'|'+fmt(means['acquisition_opportunity'])+'|'+fmt(means['total_'+t])+'|' for t in core.TAGS)
    cells = '\n'.join('|'+x['task']+'|'+x['context']+'|'+str(x['planned_boundary'])+'|3|'+
        '|'.join(fmt(x['equal_group_mean_exact'][k]) for k in ('C', 'V', 'M', 'R', 'acquisition_opportunity'))+'|' for x in result['cells'])
    text = f'''# 固定程序完整任务机会普查 v1

**事后描述性分析，使用未来结局；不是可部署选择器、可学习性或期望收益上界。**
来源manifest {MID}；原统计SHA {STAT}不变。旧接收者继续封存。
全部1740案例登记，QUAL1566，任务失败{len(result['all_task_failures'])}全部保留；29程序、261组程序行与522程序分层格完整复算。
有限菜单只包括同前缀四个固定PI时间常数×三种获取程序的12项实际完整执行，54单元、9独立组。

|CONTINUE锚点|原平均损失|固定增益记录差额|获取记录差额|合计差额|
|---|---:|---:|---:|---:|
{anchors}

C／V／M是各获取臂内四个已执行固定程序的最低记录损失，R是三臂最低；所有并列最小程序均保留。
有严格验证差额{result['overall']['validation_strictly_better']}/54，严格移动差额{result['overall']['movement_strictly_better']}/54，两者同时{result['overall']['both_strictly_better']}/54；这些计数重叠，不能相加。
C=R为{result['overall']['no_acquisition_gap']}/54；边界前成功{result['overall']['before_boundary_success']}/54保留，未删掉零机会单元。

|任务|条件|边界|独立组|C|V|M|R|获取记录差额|
|---|---|---:|---:|---:|---:|---:|---:|---:|
{cells}

完整54单元、9组、所有精确差额频数及失败见同目录JSON；原29程序逐组及522格见CSV。
差额已包含移动／验证／测量的完整在线损失，没有再加一次获取费用；实际控制步与未执行失败惩罚分别保留。
历史训练、工厂重置和模型费用沿用完整成本附录，不把本表当作完整项目资源总和。

每程序仅一次噪声实现，取事后最小值有选择乐观性；它不证明决策时可预测这些差额。
获取差额同时含状态、等待、数据与后继行为影响，不能叫纯信息收益，也不是自适应控制器最优表现的上界。
有记录差额仅支持进一步独立可学习性设计；无差额只约束该固定菜单，不否定整个A。
不得用此QUAL训练后继、调阈值、改增益、挑任务、追加样本或复活封存接收者。
原十项主比较、预测资格与任务资格原样保留；本分析没有新资格门或统计显著性检验。
新环境／reset／帧／策略／模型查询／拟合／训练／episode种子／在线LLM均0，另记文件IO和墙钟。
独立CSV／标量／Fraction复算禁用主计算函数，JSON／CSV／SHA编解码共享，没有物理重仿真。
完整原始轨迹ZIP及恢复仍待空间，本次小型分析不替代它；具体新机制、强参考部署、独立任务优势及CCF A仍未完成。
'''
    with (OUT / 'report_zh.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def worker():
    start = perf_counter_ns()
    f = admit()
    request = read(OUT / 'request.json')
    core.require(request['manifest_id'] == MID and request['source_commit'] == git('rev-parse', 'HEAD').decode().strip(), 'parent admission before actual records')
    core.require(not any((OUT / n).exists() for n in ('statistics.json', 'audit.json', 'worker_complete.json', 'failure.json')), 'one actual worker only')
    with record_only(OUT) as guard:
        verify(f['source_sha256'])
        verify(f['input_sha256'])
        original_registry = csv_read('all_1740_allocated_cases.csv')
        original_panels = csv_read('all_1566_qualified_cases.csv')
        registry, panels = core.prepare(original_registry, original_panels)
        result = core.census(registry, panels)
        write(OUT / 'statistics.json', result)
        def deny(*args, **kwargs):
            raise RuntimeError('production opportunity computation disabled during independent audit')
        with mock.patch.multiple(core, prepare=deny, census=deny, summary=deny, metrics=deny, normalize=deny, number=deny,
                                 boolean=deny, row_key=deny, unit_key=deny, require=deny):
            proof = independent.verify(csv_read('all_1740_allocated_cases.csv'), csv_read('all_1566_qualified_cases.csv'),
                read(OUT / 'statistics.json'), csv_read('all_29_programs.csv'), csv_read('all_522_task_condition_boundary_cells.csv'))
        write(OUT / 'audit.json', proof)
        write(OUT / 'registry.json', registry)
        write_csv(OUT / 'all_29_programs.csv', result['programs'])
        write_csv(OUT / 'all_261_group_programs.csv', result['group_programs'])
        write_csv(OUT / 'all_522_program_cells.csv', result['program_cells'])
        report(result)
        verify(f['source_sha256'])
        verify(f['input_sha256'])
        core.require(not any(guard.values()), 'zero forbidden operations during actual census')
        write(OUT / 'worker_complete.json', dict(integrity='PASSED_COMPLETE_POST_HOC_OPPORTUNITY_CENSUS',
            manifest_id=MID, source_primary_statistics_sha256=STAT, complete_case_denominator=1740,
            QUAL_denominator=1566, units=54, independent_groups=9, cells=18, program_cells=522,
            original_task_qualification=False, new_environment_interactions=0, new_model_queries=0,
            new_fits=0, new_episode_seed_allocations=0, online_LLM_API_calls=0,
            guard=guard, IO_counts=IO, source_hash_passes=2, wall_ns=perf_counter_ns()-start,
            post_hoc_descriptive_only=True, deployable_selector=False, publication_goal_complete=False))


def analyze():
    start = perf_counter_ns()
    admit()
    OUT.mkdir(exist_ok=False)
    source = git('rev-parse', 'HEAD').decode().strip()
    write(OUT / 'request.json', dict(source_commit=source, manifest_id=MID, worker_timeout_seconds=120,
        source_primary_statistics_sha256=STAT, one_attempt_only=True, zero_new_physics_or_fits_or_LLM=True))
    child_start = perf_counter_ns()
    try:
        with (OUT / 'stdout.log').open('xb') as stdout, (OUT / 'stderr.log').open('xb') as stderr:
            proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker'], cwd=ROOT,
                                  stdout=stdout, stderr=stderr, timeout=120)
        core.require(proc.returncode == 0, 'worker failed; preserve all outputs and do not retry')
        done = read(OUT / 'worker_complete.json')
        core.require(done['integrity'] == 'PASSED_COMPLETE_POST_HOC_OPPORTUNITY_CENSUS', 'full worker receipt')
        write(OUT / 'complete.json', dict(integrity=done['integrity'], source_commit=source,
            manifest_id=MID, worker_receipt_sha256=sha(OUT / 'worker_complete.json'),
            worker_wall_ns=perf_counter_ns()-child_start, total_parent_wall_ns=perf_counter_ns()-start,
            parent_admission_and_metadata_IO=IO, no_retry=True, new_environment_interactions=0,
            new_fits=0, online_LLM_API_calls=0, full_raw_delivery_complete=False, publication_goal_complete=False))
        print(json.dumps(dict(integrity=done['integrity'], units=54, new_environment_interactions=0, online_LLM_API_calls=0)))
    except Exception as error:
        write(OUT / 'failure.json', dict(integrity='PRESERVED_OPPORTUNITY_CENSUS_FAILURE',
            exception=type(error).__name__, reason=str(error), traceback=traceback.format_exc(),
            source_commit=source, new_environment_interactions=0, online_LLM_API_calls=0))
        raise


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    options = parser.parse_args()
    worker() if options.worker else analyze()
