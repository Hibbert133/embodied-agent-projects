"""Exact construction report and all-forecast causal availability export."""
from pathlib import Path
from time import perf_counter_ns
import csv,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_staggered_selective_scope_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.staggered_selective_reader_v2 import plain_rows
main=command.main;io=main.io;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;out=run/'presentation';out.mkdir(exist_ok=False);guard={};start=perf_counter_ns();summaries=[];flat=[]
with read_only(guard):
    audit=io.read(run/'reader_audit_v2/audit.json');assert audit['integrity']=='PASSED'
    reader_manifest=io.read(run/'reader_audit_v2/manifest.json');failed=io.read(run/'pipeline_control/audit_failure.json')
    for p in (1,2,4,8,16):
        folder=run/'construction'/('P'+str(p));summary=io.read(folder/'summary.json');summaries.append(summary);predictions={}
        for event in plain_rows(folder/'events.jsonl'):
            if event['event']=='PREDICTION':predictions[event['forecast_index']]=event
            elif event['event']=='THRESHOLD_UPDATE':
                pred=predictions[event['forecast_index']]
                flat.append(dict(delay=p,forecast_index=pred['forecast_index'],thread=pred['thread'],forecast_time=pred['time'],label_available_time=pred['label_due'],
                    threshold_numerator=pred['threshold'][0],threshold_denominator=pred['threshold'][1],warmup_complete=pred['eligible'],selected=pred['selected'],
                    miscovered_when_label_revealed=event['miscovered'],threshold_after_update_numerator=event['after'][0],threshold_after_update_denominator=event['after'][1]))
    assert len(flat)==12400
    with (out/'all12400_forecasts.csv').open('x',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    io.write(out/'research_decision.json',dict(status='REJECT_MARGINAL_COVERAGE_TO_SELECTED_ADOPTION_IMPLICATION',
        not_a_refutation_of_SI_OCP=True,not_an_algorithm_novelty_result=True,not_a_robot_harm_rate=True,
        uncertainty_reference_can_still_be_used_empirically=True,conditional_calibration_already_prior_art=True,
        new_collection_unlocked=False,old_closed_versions_not_reopened=True,full_CCF_A_goal_complete=False))
    io.write(out/'literature_reading.json',dict(classification='PARTIAL_PRIMARY_READING_NOT_REPRODUCTION',sources=[
        dict(url='https://arxiv.org/html/2604.06058v1',read='Abstract, II/III, Assumptions1/2, formulas4-13, associated proof and conclusion',limit='No quadrotor/DNN reproduction or theorem refutation'),
        dict(url='https://arxiv.org/html/2603.02196v3',read='Abstract/introduction recheck; earlier official PDF reading preserved in information_release_prior_art',limit='No guarantees transferred'),
        dict(url='https://arxiv.org/abs/2101.01739',read='Official abstract',limit='No full proof/reproduction'),
        dict(url='https://proceedings.neurips.cc/paper_files/paper/2022/hash/bcdaaa1aec3ae2aa39542acefdec4e4b-Abstract-Conference.html',
            read='Official abstract, plus earlier PDF search-returned1.1/2 setting paragraphs',limit='Threshold-conditional coverage already exists; no implementation or finite stopping guarantee inferred')],novelty_established=False))
    table='| 延迟P | 预测/已揭晓标签 | 主阈值更新 | 热身后被选数 | 全部预测覆盖 | 被选预测覆盖 | 首个被选标签揭晓时刻 |\n| --- | --- | --- | --- | --- | --- | --- |\n'
    for s in summaries:
        c=s['counts'];table+=f"| {s['delay']} | {c['predictions']}/{c['labels']} | {c['updates']} | {c['selected']} | 19/20 | 0/1 | {s['first_selected_label_due']} |\n"
    receipt=io.read(run/'construction/receipt.json');cost=dict(constructed_forecasts=12400,constructed_events=37210,primary_threshold_calibration_updates=12400,
        independent_integer_reconstruction_updates=12400,primary_wall_seconds=receipt['wall_ns']/1e9,independent_wall_seconds=audit['wall_ns']/1e9,first_failed_reader_wall_seconds=failed['wall_ns']/1e9,first_failed_reader_integer_updates=0,
        new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_task_seeds=0,new_random_sampling=0,new_model_fits=0,fixed_policy_queries=0,
        online_LLM_API_calls=0,new_unit_tests_claimed=0,source_bound_reused_unique_tests=2228)
    io.write(out/'costs.json',cost)
    text=f'''# A线：长期覆盖与选择采用的精确范围检查 v1

**本轮为构造性数学范围检查，不是机器人试验、SI-OCP复现、新算法或任务收益。** 结果否定的仅是“长期边际覆盖95%足以保证按低阈值选择/停止后也有95%覆盖”的推论。它没有反驳SI-OCP原论文的长期结论，也不证明机器人有害更新率为100%。

主构造冻结 `{m['source_git_commit']}`；只读读取修复冻结 `{reader_manifest['source_git_commit']}`。运行 `{run.relative_to(ROOT).as_posix()}`。不解析TRAIN/CAL/TEST/QUAL机器人内容，不拟合模型，不救回旧响应/ARX/F20/成对上下文或原生失败版本。

## 精确结果

{table}

五种预定延迟全部保留，共12400个构造预测、12400个到期标签、主12400次阈值更新和独立12400次整数复算。共589个热身后被选预测全部未覆盖；全部12400预测却正好95%覆盖。线程与轮数不是独立机器人样本，不作显著性检验或蒙特卡洛置信区间。

选择只依据当时已有阈值，且每线程先完成20轮完整热身。当前分数按预先固定的时刻规则产生，恰在预测P个时间单位后才公开，不由选择结果临时修改。首个被选标签在21P时揭晓；所有情形中最多336个构造时间单位，并非机器人控制步。停止于首个被选预测同样不能从长期覆盖直接得到保证。

## 为什么得到这个结果

α=1/20，η=1，初始q=0。每条交错线程每20轮的第一轮分数为1，其余分数为0。递推q←q+1(S>q)−1/20全部使用精确Fraction。周期第一轮q=0、分数1未覆盖，随后q成为19/20；接下来的19个零分数依次将q降回0。因此每周期恰一次未覆盖，长期及本次有限完整周期的边际覆盖均为19/20。

热身后选择规则为“当时q=0就选择”。它恰好选中每周期那次未覆盖预测，所以选后覆盖为0。阈值始终在0与19/20间，不依赖负数阈值、数值误差、未来信息、缺失标签或跳过热身。每线程的望远镜恒等式q_end−q_start=misses−αN=0也独立核对。

这个例子针对的是**不同统计目标之间的错误推导**。全体预测覆盖、选择子集覆盖、数据依赖停止时的单次覆盖、物理安全和包含获取成本的任务收益是不同量。区间未覆盖不等于该次纠正使任务变坏；即使获得选后覆盖，也不能因此替代独立完整任务损失比较。

## 原论文和已有更强路线

[SI-OCP原文](https://arxiv.org/html/2604.06058v1)使用积分分数与交错延迟阈值，并依赖残差时间Lipschitz、已测状态和递归可行控制器等条件。它的长期结论没有承诺本文所反驳的选后单次目标。本项目离散观测、白噪声、接触和隐藏状态不能自动满足其假设，未复现其四旋翼或DNN实验；本构造不是该算法的完整实现或定理反例。

条件覆盖本身已有研究：[Online Multivalid Learning](https://arxiv.org/abs/2101.01739)给出在线分组条件预测框架；[Practical Adversarial Multivalid CP](https://proceedings.neurips.cc/paper_files/paper/2022/hash/bcdaaa1aec3ae2aa39542acefdec4e4b-Abstract-Conference.html)官方摘要明确包含阈值条件与特征分组的经验覆盖。[CPC](https://arxiv.org/html/2603.02196v3)也已研究风险控制及策略变化。本轮只读指定部分，不把这些方法的假设或保证移植到机器人，不声称发现了新的选择偏差理论。

## 完整记录、审计和费用

每个延迟目录保留INITIAL、PREDICTION、LABEL、THRESHOLD_UPDATE和COMPLETE共37210个有序事件；全部预测、阈值、选择、标签可用时刻及揭晓后误差见 `presentation/all12400_forecasts.csv`。主有理数生成器在独立审计时被禁用，第二实现用1/20整数单位、独立约分和完整事件重建，核对严格字段、预测先于标签、延时/更新次序、分母、选择、覆盖和终端阈值通过。共享JSON解析与无物理守卫已披露，非独立研究机构认证。

原独立读者在首条事件前把明文JSONL误作gzip而失败，原pipeline失败保留。另行冻结v2只修正读取和输出位置，全部整数数学不变，主生成器被禁用，全部原记录SHA保持；没有重新构造。原失败耗时{cost['first_failed_reader_wall_seconds']:.3f}秒、整数更新0，另列于费用。主耗时{cost['primary_wall_seconds']:.3f}秒，v2独立耗时{cost['independent_wall_seconds']:.3f}秒。新增环境创建、重置、控制步、物理帧、机器人种子、随机采样、模型拟合、固定政策查询、在线LLM API均0。**主12400次阈值校准更新和独立12400次整数更新已单列**，不谎称没有数值更新。旧2228项仅按源码哈希复用，新增unittest计数为0，数学验证来自完整精确重建；不重复旧仿真。

源码/配置/协议先冻结后运行一次，来源SHA、各阶段意图与回执保留。提交前完成编译、依赖、全仓秘密与实际索引补充扫描、普通/暂存差异、Git/磁盘字节核对；原始记录及旧失败保持不变，按授权习惯紧凑归档。测试、审计和归档不是论文贡献。

## 研究决定

关闭“给旧纠正加一个长期边际覆盖门控即可获得选后可靠性或新方法”的主张。保留正确使用的OCP/MVP/CPC等标准参考；不据此否定所有自适应验证，也不启动新的机器人人口。

真正候选仍须说明：当前可见数据能支持哪种采用目标、验证后的真实状态/控制记忆如何改变该目标、哪些反馈实际可获得、以及如何以同预算和完整损失超过强参考。若主张选后校准，必须面对相应条件/选择/延迟参考；若主张任务收益，必须实测DIRECT_C8、积分、廉价固定程序、完整免费历史、始终获取/不更新、检测/历史辨识和完整成本Q/DR等对照。

原MDE/Residual RL/OCCAM/GAUGE/Poke/TOM、AA-POMDP、MIAC/任务实验设计、VoSI/SPO/performative prediction等查新继续有效。当前尚无查新成立的新机制，也没有独立自身历史完整成本优势与消融。完整CCF A目标继续活跃，未被这项数学检查缩小或完成。
'''
    report=ROOT/'reports/staggered_selective_scope_v1_zh.md';report.write_text(text,encoding='utf8',newline='\n')
io.write(out/'report_receipt.json',dict(integrity='FOR_DELIVERY_AUDIT',report_sha256=io.sha(report),all12400_forecasts_exported=True,guard=guard,
    new_physics=0,new_model_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
print(dict(integrity='EXACT_RESULT_RECORDED',forecasts=12400,selected=589,report=str(report)),flush=True)
