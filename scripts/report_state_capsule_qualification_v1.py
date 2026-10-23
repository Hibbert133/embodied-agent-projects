"""Chinese success/incomplete qualification report from saved artifacts only."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_strong_chronological_reference_v1 as io


def report(path):
    m=io.read(path);folder=path.parent/'collection';s=io.read(folder/'summary.json')
    audit_path=path.parent/'audit.json';a=io.read(audit_path) if audit_path.exists() else None
    passed=a is not None and a['integrity']=='PASSED' and a['summary_sha256']==io.sha(folder/'summary.json')
    if a is not None and not passed:raise ValueError('mismatched audit')
    counts=s['lifecycle']['counts']
    lines=['# 同一决策状态恢复：工程资格 v1','',
        ('**注册恢复合同通过。**' if passed else '**资格未通过或尚未完成审计。**')+
        '本轮是评价者采集工具，不是新控制器、任务收益比较、真实硬件验证或普遍隐藏状态证明。',
        '',f"实际创建／记录{len(s['cases'])}个上下文，实际控制{s['actual_controlled_steps']}步、受控重置{s['actual_controlled_resets']}次、"
        f"全部重置{counts.get('reset_completed',0)}次、请求模拟帧{counts.get('simulation_frames_attempted',0)}个。",
        '',f"恢复{s['restore_calls']}次，捕获累计{s['capture_wall_ns']/1e9:.6f}秒、恢复累计{s['restore_wall_ns']/1e9:.6f}秒；"
        f"政策查询{s['policy_queries']}次。序列化负载与Python数组缓冲大小逐上下文保存。"
        '工厂初始化与所有真实重复分支均计费，物理费用账本不回退。',
        '', '| 上下文 | 任务 | 前缀步数 | 已执行分支 | 分支实际步数 |','|---:|---|---:|---:|---|']
    for r in s['cases']:lines.append(f"| {r['case']} | {r['task']} | {r['prefix_steps']} | {len(r['branches'])} | "+','.join(str(len(b['trace'])) for b in r['branches'])+' |')
    if passed:lines+=['',f"独立记录审计通过{a['events_checked']}个事件和{a['matched_continuation_pairs']}对重复轨迹；"
        f"审计另查询政策{a['audit_policy_queries']}次，新增环境交互0。"
        '它重建命令、私有噪声、模拟时钟和真实费用，不调用胶囊实现或创建环境。']
    if s['failure'] is not None:lines+=['',f"原样保留失败：`{s['failure']}`。未重跑原种子、放宽条件或把部分结果当通过。"]
    lines+=['','实现保留原生对象地址，复制完整mjModel／mjData，并恢复任务、包装器、政策、'
        'RNG和共享数组关系。恢复前的主动扰动必须被消除。未知对象、改变的所有者、ABI、'
        '胶囊、类状态、回调、插件或活动渲染均拒绝。胶囊不从外部文件加载。',
        '', '统计包装器的info.episode.t来自不可回退墙钟，原值保留，单独排除轨迹相等比较；'
        '奖励、成功、观测、终止、累计奖励、长度、RNG见证和模拟时钟均比较。'
        '事件时间戳与费用另审计，不要求重复的物理耗时相同。',
        '', '本轮API、名义拟合、选择器拟合和政策更新均0。新种子18800–18811只执行一次，'
        '18812–18999及全部旧保留未用。软件夹具和检查不是这12个MetaWorld上下文。',
        '', '`universal_complete_hidden_state_qualification=false`保持不变；有限测试不证明任意'
        '未知状态的完整性，旧数据资格不升级。后继多未来标签、行为覆盖、条件价值误差、'
        '新方法机制、独立确认和完整论文仍需推进。',
        '', f"运行：`{m['experiment_run_id']}`；清单：`{m['manifest_id']}`；冻结：`{m['source_git_commit']}`。",'']
    target=ROOT/'reports/state_capsule_qualification_v1.md'
    with target.open('x',encoding='utf-8',newline='\n') as handle:handle.write('\n'.join(lines))
    io.write(path.parent/'report_provenance.json',{**{k:m[k] for k in io.IDENTITY},'report_path':target.relative_to(ROOT).as_posix(),
        'report_sha256':io.sha(target),'summary_sha256':io.sha(folder/'summary.json'),'audit_sha256':io.sha(audit_path) if a else None,
        'registered_restore_contract_passed':passed,'universal_complete_hidden_state_qualification':False},exclusive=True)
    print(target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);args=parser.parse_args();report(args.manifest.resolve())
