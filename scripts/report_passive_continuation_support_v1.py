"""Present audited JSON only; no policies, fitting or physical capabilities."""
from pathlib import Path
from time import perf_counter_ns
import argparse,json,hashlib

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/passive_continuation_support_v1_zh.md'
TASK={'push-v3':'推物','reach-v3':'到达','door-open-v3':'开门'}
CONTEXT={'UNCHANGED':'不变','CHANGED':'变化'}


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def table(head,rows):return '\n'.join(['|'+'|'.join(head)+'|','|'+'|'.join(['---']*len(head))+'|',*('|'+'|'.join(str(t) for t in row)+'|' for row in rows)])


def main(path):
    start=perf_counter_ns();out=path.parent;m=read(path);summary=read(out/'summary.json');audit=read(out/'audit.json')
    assert audit['integrity']=='PASSED' and audit['manifest_id']==m['manifest_id']
    for n,h in audit['analysis_artifact_sha256'].items():assert sha(out/n)==h,n
    rows=read(out/'reference_replays.json');registry=read(out/'case_registry.json');qa=read(ROOT/'outputs/passive_continuation_support/validation_v2/complete.json')
    groups=[]
    for cohort in ('SOFTWARE_NATIVE','QUAL'):
        selected=[r for r in rows if r['cohort']==cohort]
        groups.append((cohort,len(selected),sum(r['available_validation_steps']==8 for r in selected),sum(0<r['available_validation_steps']<8 for r in selected),sum(r['available_validation_steps']==0 for r in selected),sum(r['source_steps'] for r in selected)))
    missing=[r for r in rows if r['missing_reason']];failures=[r for r in registry if not r['original_success']]
    summary_table=table(['来源','规范轨迹','完整8步','短窗口','无窗口','来源真实命令步'],groups)
    panels=table(['来源','任务','条件','时点','完整分母','完整/短/无','实际窗口步'],[
        (p['cohort'],TASK[p['task']],CONTEXT[p['context']],p['boundary'],p['complete_denominator'],f"{p['full_windows']}/{p['short_windows']}/{p['unavailable_windows']}",p['actual_window_steps']) for p in summary['panels']])
    unavailable=table(['来源','组','任务','条件','种子','边界','实际总步','窗口步','原因'],[
        (r['cohort'],r['group'],TASK[r['task']],CONTEXT[r['context']],r['seed'],r['planned_boundary'],r['source_steps'],r['available_validation_steps'],r['missing_reason']) for r in missing])
    historical_failures=table(['来源','组','任务','条件','种子','程序','实际步','截止损失'],[
        (r['cohort'],r['group'],TASK[r['task']],CONTEXT[r['context']],r['seed'],r['program'],r['original_steps'],r['original_deadline_loss']) for r in failures])
    text=f'''# 正常继续与八步验证：完整保存轨迹语义核对

2026-10-23；**全部新增分析均为事后描述性分析**，没有新机器人实验或模型训练。

## 结论及纠正

在全部72条预先指定的RAW_CONTINUE规范轨迹上，RAW、VALIDATE_NO_UPDATE和
TAIL_VALIDATE8_1的完整发送命令、每步控制记忆、最终状态与截止损失完全一致。
共核对8,921个实际来源命令，216次离线程序复演；没有借用不同命令之后的结果。
这说明**当前固定控制参数的VALIDATE8只是正常任务继续，改变的是阶段/信息标签**。
它不证明新测量、学习反馈或真正有辨识激励的获取动作没有价值。

进一步核对后需纠正一个研究解释：关闭草案的20程序中本来已经包含
`VALIDATE_FULL`。它正可解释为“正常执行八步后，用已获得历史选择增益”的被动
延后适应参考，**不是新增缺失基线**。不能把DEFER8另起名字再计成一个独立对照
或新增样本，也不能将验证分支相对固定控制的优势单独称为主动探测优势。
此前进展中“补上一个强对照”的说法应以本报告这一更准确说明为准。

本次逐轨迹实证限定在0.5秒增益不变。对于真正选择不同增益的学习接收者，
只要正常继续与验证读取同一公共历史、同一控制记忆，并采用相同接收函数，
就可定义同机会的被动参考；**本次没有在旧轨迹上推算其未执行任务结局**。
单个命令相同也不能保证以后都相同；测试在首个发送差异处停止，不披露下一结果。

## 完整人口、窗口与分层

来源全630次执行均登记；其它558次程序标为非该规范来源，未当作额外RAW样本。
分析全部72条RAW_CONTINUE，不按成功、失败、扰动条件或窗口长度筛选。
共有59个完整窗口、5个短窗口、8个边界前/恰在边界结束案例。
长轨迹没有被当成更多独立样本；这里只做机械一致性核对，不做任务收益显著性检验。

{summary_table}

以下36格完整展示两来源阶段×三任务×两条件×三个边界；“完整/短/无”保留全部分母。

{panels}

## 全部短/缺失窗口

没有窗口不是零位移；结束后不再构造八个观测或声明探测已完成。

{unavailable}

## 可用信息和复演边界

主程序只得到真实当前观测、对应时点的已保存原始策略动作，以及保存的控制记忆。
不重新查询底层政策，不接收扰动参数、实际执行噪声、私有状态、种子或未来结局。
评估端可预载完整文件；下一观测只有在当前发送命令与历史实际float32命令精确
相等后才披露。合成拒绝检查还将未披露的下一观测破坏，确认首个命令分歧不会
访问该结果。这里没有用容差把不同命令强行视为相同，也没有环境恢复或物理重跑。

VALIDATE_NO_UPDATE将其中实际0–8个任务步标成验证，RAW把同一批步标成正常任务。
总实际步和失败罚已经在完整截止损失中计一次；不能额外加8来制造费用差异。
TAIL_VALIDATE8_1释放额外轨迹但仍固定同一控制参数，因此物理结局相同；这不是
已训练接收者的表现或真实原生随机释放资格。全部新计划时间戳只是软件复演顺序，
不能冒充新测得的物理时钟。

## 独立审计、来源与费用

分析冻结`{m['source_git_commit']}`；运行`{m['analysis_run_id']}`；
清单`{m['manifest_id']}`。旧来源清单和压缩字节通过原审计绑定，并在本轮前后
核对SHA-256。原六项比较、全部负结果、原始记录、分片和恢复副本均未改写。

独立审计关闭主执行器、主复演和PIPlan.numbers，另写解析和逐步PI算术，
核对{audit['fields_checked']:,}个标量字段通过，覆盖630登记、72全轨迹、216复演、
全部真实窗口及36格。两级记录证明当前软件/语义，不证明预测能力或任务收益。

主分析核心耗时{summary['wall_ns']/1e9:.6f}秒，独立审计核心耗时{audit['wall_ns']/1e9:.6f}秒。
离线保存策略动作读取26,763次；独立PI复算8,921步；冻结前首个预定保存轨迹的
软件兼容检查另复算62步，不作为新机器人样本。数组测试的常规运算和耗时另见日志。
新增环境创建、控制步、全部重置、物理帧、模型拟合、优化更新、固定策略重新查询、
新种子和在线LLM API均为0；两个运行守卫均未记录禁用操作或网络尝试。

旧630次研究已付81,042控制步、32,130全部重置、16,470,210物理帧；本次规范
8,921步是其中子集，不能再加为新交互。来源阶段的训练/调参费用仍按旧报告保留，
本分析不将其记成零或重新收费。

13项新增检查通过，旧2,009项绑定来源哈希复用，累计{qa['cumulative_unique_tests']:,}项独特检查；
旧6组张量检查另列，未重复旧仿真。首次开发检查的元组/JSON列表断言失败以及
冻结v1的配置元组/列表比较失败均原样保留；修复均在正式冻结前，没有改科学
比较、阈值、精度容差或旧来源。编译、依赖、秘密扫描和普通/暂存差异回执保留。

## 查新及下一阶段

[OCCAM §3–4.3](https://arxiv.org/html/2406.17620v1)已经以历史观测/输入、任务和控制
增益预测表现，并定期优化增益；本项目的被动历史适应不能只换名字宣称新颖。
[Conditional Importance Sampling，AISTATS 2020](https://proceedings.mlr.press/v108/rowland20b.html)
的出版摘要已给出条件重要性采样框架；轨迹/动作等价与方差减少不是自动的新估计器。
[Dual Control Reference Generation](https://arxiv.org/abs/2510.20483)的摘要/引言
已讨论把适应机制放入参考轨迹设计，兼顾任务执行与辨识。本次没有复现上述方法，
也未通读后两文全部证明；不能宣称它们不处理物理影响。

用户指定的模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike，以及
DISaM、CPC、MIPS等既有边界继续有效。原M/D回归的DR等价淘汰不变，旧ARX、SS、
固定时点清零负结果不被本报告重开。物理获取、返回后的模型适用性和实际采用/拒绝
仍须一起进入完整任务评价；拟合误差、合法参数或这次命令一致不能替代收益。

后续先寻找**真实改变辨识激励或可用观测、且可超过同机会被动适应**的机制。
任何新控制器/获取程序都须单独冻结训练、校准、独立自身时序评价、完整费用和
失败处理，并保留现有强控制。不能通过新增一个已有程序的别名、屏蔽免费历史、
降低基线或复用旧QUAL调参来完成目标。本次是对实验解释的收紧，CCF A目标未完成。

## 全部历史任务失败登记

以下{len(failures)}个是原630次研究中的任务失败，均完整保留；不是本次新增失败。
完整登记和来源链接位于运行目录的case_registry.json、manifest.json；停止原因
及逐步记录仍见原cases/events文件，未用此表替代原始案例。

{historical_failures}
'''
    with REPORT.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    receipt=dict(integrity='PASSED',report=REPORT.relative_to(ROOT).as_posix(),report_sha256=sha(REPORT),
        audited_artifacts_sha256=audit['analysis_artifact_sha256'],auditor_sha256=sha(out/'audit.json'),
        all36_panels_included=True,all_short_or_missing_windows_included=len(missing),all_historical_task_failures_included=len(failures),
        changed_gain_outcomes_imputed=0,new_physical_activity=0,model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start)
    with (out/'report_receipt.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
    print({k:receipt[k] for k in ('integrity','all_short_or_missing_windows_included','all_historical_task_failures_included')},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);main(parser.parse_args().manifest)
