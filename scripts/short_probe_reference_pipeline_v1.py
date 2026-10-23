"""Five sequential frozen stages, with separate record and numeric readers."""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import short_probe_study_io_v1 as io
from src.analysis.short_probe_study_v1 import statistics, costs
from src.analysis.short_probe_numeric_audit_v1 import reconstruct, compare


def context(path, phase):
    m,_,_ = io.load(path);folder = path.parent;identity = {k:m[k] for k in io.IDENTITY}
    summary_path = folder/phase.lower()/'summary.json';summary = io.read(summary_path)
    audit_path = folder/(phase.lower()+'_record_audit.json');audit = io.read(audit_path)
    if any(v[k] != m[k] for v in (summary,audit) for k in io.IDENTITY) or audit['phase'] != phase or audit['integrity'] != 'PASSED' or audit['summary_sha256'] != io.sha(summary_path):
        raise ValueError('complete independently audited summary required')
    return m,folder,identity,summary,audit


def csv_write(path, rows, fields):
    with path.open('x',encoding='utf-8',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def analyze(path, phase):
    m,folder,identity,summary,_ = context(path,phase);out = folder/(phase.lower()+'_analysis');out.mkdir()
    io.write(out/'statistics.json',{**identity,**statistics(summary['rows'],phase)})
    io.write(out/'costs.json',{**identity,**costs(summary)})
    fields = list(summary['rows'][0])
    csv_write(out/'all_executions.csv',summary['rows'],fields)
    csv_write(out/'all_failures.csv',[r for r in summary['rows'] if not r['success']],fields)
    csv_write(out/'all_stops.csv',[r for r in summary['rows'] if r['stopped']],fields)
    io.write(out/'analysis_completion.json',{**identity,'phase':phase,
        'summary_sha256':io.sha(folder/phase.lower()/'summary.json'),
        'record_audit_sha256':io.sha(folder/(phase.lower()+'_record_audit.json')),
        'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir()}})


def numeric(path, phase):
    _,folder,identity,summary,audit = context(path,phase);out = folder/(phase.lower()+'_analysis')
    completion = io.read(out/'analysis_completion.json')
    expected_names = {'statistics.json','costs.json','all_executions.csv','all_failures.csv','all_stops.csv'}
    if any(completion[k] != identity[k] for k in io.IDENTITY) or completion['phase'] != phase or set(completion['artifact_sha256']) != expected_names or completion['summary_sha256'] != audit['summary_sha256'] or completion['record_audit_sha256'] != io.sha(folder/(phase.lower()+'_record_audit.json')):
        raise ValueError('analysis receipt differs')
    if any(io.sha(out/name) != sha for name,sha in completion['artifact_sha256'].items()):
        raise ValueError('analysis bytes changed')
    stat,fees = reconstruct(summary)
    checks = compare({'statistics':io.read(out/'statistics.json'),'costs':io.read(out/'costs.json')},
                     {'statistics':{**identity,**stat},'costs':{**identity,**fees}})
    # CSVs are full materialized rows, not a filtered best-case presentation.
    for name,rows in (('all_executions.csv',summary['rows']),('all_failures.csv',[r for r in summary['rows'] if not r['success']]),
                      ('all_stops.csv',[r for r in summary['rows'] if r['stopped']])):
        with (out/name).open(encoding='utf-8',newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != list(summary['rows'][0]) or list(reader) != [{k:str(v) for k,v in r.items()} for r in rows]:
                raise ValueError('CSV population differs: '+name)
    io.write(folder/(phase.lower()+'_numeric_audit.json'),{**identity,'phase':phase,'integrity':'PASSED',**checks,
        'summary_sha256':audit['summary_sha256'],'record_audit_sha256':io.sha(folder/(phase.lower()+'_record_audit.json')),
        'statistics_sha256':io.sha(out/'statistics.json'),'costs_sha256':io.sha(out/'costs.json'),
        'analysis_completion_sha256':io.sha(out/'analysis_completion.json'),
        'csv_rows_checked':len(summary['rows'])+sum(not r['success'] for r in summary['rows'])+sum(r['stopped'] for r in summary['rows']),
        'shared_numeric_helpers':['NumPy registered PRNG and quantile'], 'new_environment_steps':0,'new_api_calls':0})


def report(path, phase):
    _,folder,identity,summary,audit = context(path,phase);out = folder/(phase.lower()+'_analysis')
    checked = io.read(folder/(phase.lower()+'_numeric_audit.json'));stat = io.read(out/'statistics.json');fees = io.read(out/'costs.json')
    if any(checked[k] != identity[k] for k in io.IDENTITY) or checked['integrity'] != 'PASSED' or checked['phase'] != phase or checked['summary_sha256'] != audit['summary_sha256'] or checked['statistics_sha256'] != io.sha(out/'statistics.json') or checked['costs_sha256'] != io.sha(out/'costs.json') or checked['record_audit_sha256'] != io.sha(folder/(phase.lower()+'_record_audit.json')):
        raise ValueError('passed and unchanged numeric audit required')
    title = '预检' if phase == 'SMOKE' else '主实验'
    lines = [f'# 四步与八步标准基线比较：{title}', '',
        f"运行 `{identity['experiment_run_id']}`；清单 `{identity['manifest_id']}`；冻结提交 `{identity['source_git_commit']}`。", '',
        f"完成 {stat['units']} 个单元、{stat['executions']} 次方法执行，全部保留在分母中。记录审计与独立统计复算通过。",
        '本轮检验便宜标准基线，不提出新算法。API 调用为零；不构成 LLM 提升或 CCF A 发表证据。', '',
        '| 方法 | 成功/全部 | 失败 | 其中停止 | 平均截止损失 | 平均实际步数 | 平均探测步数 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for method,v in stat['methods'].items():
        lines.append(f"| {method} | {v['successes']}/{v['cases']} | {v['failures']} | {v['stops']} | {v['mean_deadline_loss']:.4f} | {v['mean_total_steps']:.4f} | {v['mean_fixed_probe_steps']:.4f} |")
    lines += ['', '成功按实际总步数计分；失败与停止的截止损失均为 500。实际费用只计真实执行，停止没有补齐到 500 步。', '',
        '| 左侧方法 − 右侧方法 | 平均损失差/步 | 95%完整流区间 | 地位 |', '|---|---:|---|---|']
    for v in stat['contrasts']:
        interval = '单流预检不估计总体区间' if v['ci95'] is None else f"[{v['ci95'][0]:.4f}, {v['ci95'][1]:.4f}]"
        lines.append(f"| {v['left']} − {v['right']} | {v['mean_loss_difference']:.4f} | {interval} | {'主比较' if v['primary'] else '未多重校正的次比较'} |")
    lines += ['', '差值为负表示左侧损失更低。主实验按九个故障/变化格内各六条完整流进行 10,000 次配对重采样；',
        '预检仅一条流，用于检查流程，不能据分数选方法或调整阈值。样本量使用历史方差代理，不能据不显著结果宣称等效。', '',
        f"实际四步拟合并消费其参数执行政策的链路有 {len(audit['four_step_policy_chains'])} 条。",
        f"实际补测回退单元有 {sum(v['fallback_probe_extension_observed'] for v in audit['matched_units'])} 个；未完成的配对前缀有 {sum(v['incomplete_prefix_pairs'] for v in audit['matched_units'])} 对，保留提前结束原因。", '',
        '完整失败清单包括所有失败和停止，不只列举代表案例：', '',
        f"- [全部执行](../../{(out/'all_executions.csv').relative_to(ROOT).as_posix()})",
        f"- [全部失败](../../{(out/'all_failures.csv').relative_to(ROOT).as_posix()})",
        f"- [全部停止](../../{(out/'all_stops.csv').relative_to(ROOT).as_posix()})", '',
        '| 方法 | 在线步数 | 全部重置 | 请求帧 | 在线拟合/nfev | 设计核对候选 | 每单元历史来源步数 |', '|---|---:|---:|---:|---|---:|---:|']
    for method,v in fees['methods'].items():
        lines.append(f"| {method} | {v['online_environment_steps']} | {v['online_all_reset_calls']} | {v['online_simulation_frames']} | {v['online_parameter_fits']}/{v['optimizer_nfev']} | {v['design_verification_candidates']} | {v['prior_source_steps_per_unit']:.4f} |")
    counts = summary['lifecycle']['counts']
    lines += ['', f"总计实际控制 {summary['controlled_steps']} 步，全部重置 {counts['reset_completed']} 次，请求仿真帧 {counts['simulation_frames_attempted']}；采集耗时 {summary['wall_ns']/1e9:.2f} 秒。",
        '每个环境含 50 次任务生成重置及一次受控初始重置。六种依赖名义模型的方法各承担完整历史来源：',
        f"3,840 步、480 次受控重置、24,480 次全部重置、12,259,200 请求帧，按本阶段 {stat['units']} 单元摊销；NO_PROBE 为零。",
        '历史来源实际采集一次，不算本轮新增。探测动作设计此前枚举三次、共 432 候选；每次 DOPT 执行的核对重算另列。',
        f"审计额外重算：{audit['audit_recomputation']}。这些是计算费用，审计没有新增环境步、重置或 API 调用。", '',
        '所有方法从各自受控重置开始；不带跨单元缓存，不能据本轮评价时序记忆或变化检测。',
        '匹配核对使用初始物理见证、可见观测和实际探测前缀；日志见证来自执行进程，不是独立物理复现或完整隐藏状态证明。',
        '审计共享已披露的估计器、设计、固定政策及随机数/数值函数；外层分配、顺序、消费关系和统计聚合另行实现。',
        '新贡献、独立新方法验证、消融和完整论文仍未完成。', '']
    destination = ROOT/'reports/short_probe_reference'/f'{phase.lower()}_v1.md';destination.parent.mkdir(exist_ok=True)
    with destination.open('x',encoding='utf-8',newline='\n') as f:
        f.write('\n'.join(lines))
    io.write(out/'report_receipt.json',{**identity,'phase':phase,'report_path':destination.relative_to(ROOT).as_posix(),
        'report_sha256':io.sha(destination),'record_audit_sha256':io.sha(folder/(phase.lower()+'_record_audit.json')),
        'numeric_audit_sha256':io.sha(folder/(phase.lower()+'_numeric_audit.json'))})


def pipeline(path, phase):
    io.clean();m,_,_ = io.load(path)
    if io.git('rev-parse','HEAD') != m['source_git_commit']:
        raise ValueError('pipeline requires frozen source commit')
    folder = path.parent;logs = folder/(phase.lower()+'_pipeline');logs.mkdir()
    receipt = {**{k:m[k] for k in io.IDENTITY},'phase':phase,'status':'RUNNING','steps':[],
        'started_utc':datetime.now(timezone.utc).isoformat(),'failure':None}
    steps = [('collect','scripts/run_short_probe_reference_v1.py','run'),
        ('record_audit','scripts/audit_short_probe_reference_v1.py',None),
        ('analyze','scripts/short_probe_reference_pipeline_v1.py','analyze'),
        ('numeric_audit','scripts/short_probe_reference_pipeline_v1.py','numeric'),
        ('report','scripts/short_probe_reference_pipeline_v1.py','report')]
    io.write(folder/(phase.lower()+'_pipeline_status.json'),receipt)
    try:
        for name,script,command in steps:
            args = [sys.executable,str(ROOT/script)]+([] if command is None else [command])+['--manifest',str(path),'--phase',phase]
            started = perf_counter_ns();print(f'{phase}: {name}',flush=True)
            with (logs/(name+'.txt')).open('xb') as f:
                result = subprocess.run(args,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
            receipt['steps'].append({'stage':name,'returncode':result.returncode,'wall_ns':perf_counter_ns()-started,
                'log_sha256':io.sha(logs/(name+'.txt'))})
            io.write(folder/(phase.lower()+'_pipeline_status.json'),receipt,exclusive=False)
            if result.returncode:
                raise RuntimeError(f'{name} failed; preserve one-shot artifacts')
        receipt['status'] = 'COMPLETED_FOR_REVIEW'
    except BaseException as error:
        receipt.update(status='FAILED_PARTIAL',failure={'type':type(error).__name__,'message':str(error)})
        raise
    finally:
        receipt['ended_utc'] = datetime.now(timezone.utc).isoformat()
        io.write(folder/(phase.lower()+'_pipeline_completion.json'),receipt)
        io.write(folder/(phase.lower()+'_pipeline_status.json'),receipt,exclusive=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('command',choices=('analyze','numeric','report','pipeline'))
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--phase',choices=('SMOKE','MAIN'),required=True)
    a = p.parse_args();globals()[a.command](a.manifest.resolve(),a.phase)
