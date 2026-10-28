"""Report the one frozen training and independent numerical export audit."""
from pathlib import Path
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
RUN=c.OUTPUT/'occam_reference_train_v3_20261028T071949Z_c92356173d9e'
OUT=c.BASE/'learning_delivery_v1'


def main():
    OUT.mkdir(exist_ok=False);spec=c.read(RUN/'learning_spec.json');result=c.read(RUN/'learning/complete.json')
    audit=c.read(RUN/'learning/model_audit.json');process=c.read(RUN/'learning_process_v1/complete.json')
    assert result['integrity']==audit['integrity']=='PASSED' and process['returncode']==0
    assert result['counters']['Adam_updates']==result['counters']['optimizer_step_attempts']==9000
    assert result['Torch_solve_attempts']==result['counters']['inner_filter_updates']==66712
    assert result['allocated_episodes']==648 and result['nonempty_episodes']==542
    assert audit['independent_analysis_solves']==918 and all(v['episodes']==16 for v in audit['checks'].values())
    assert result['public_source_sha256']==audit['source_public_sha256']==spec['public_sha256']
    for name,h in spec['learning_source_sha256'].items():assert c.sha(ROOT/name)==h
    for label,hashes in result['checkpoints'].items():
        for suffix,key in (('raw','raw_sha256'),('normalized','normalized_sha256')):
            assert c.sha(RUN/'learning'/(label+'_'+suffix+'.json'))==hashes[key]
    paths={p for p in (RUN/'learning').iterdir() if p.is_file()}|{p for p in (RUN/'learning_process_v1').iterdir() if p.is_file()}
    paths.add(RUN/'learning_spec.json')
    for name in ('prepare-learning_None_attempt01','model-audit_None_attempt01'):
        entry=RUN/'entry_attempts_v1'/name;assert c.read(entry/'complete.json')['integrity']=='PASSED'
        paths|={p for p in entry.iterdir() if p.is_file()}
    c.write(OUT/'source_manifest.json',dict(integrity='PASSED',manifest_id=spec['source_manifest_id'],
        files={p.relative_to(ROOT).as_posix():dict(bytes=p.stat().st_size,sha256=c.sha(p)) for p in sorted(paths)},
        scientific_source_sha256=spec['learning_source_sha256'],public_source_sha256=spec['public_sha256'],
        no_checkpoint_selection=True,new_model_training_repeated=False,online_LLM_API_calls=0))
    table='\n'.join('|'+name+'|'+str(row['episodes'])+'|'+format(row['max_basis_difference'],'.3g')+'|'+format(row['max_prediction_difference'],'.3g')+'|'+format(row['max_batch_posterior_difference'],'.3g')+'|' for name,row in audit['checks'].items())
    report=f'''# 标准表现参考v3：完整训练与独立数学核对

2026-10-28。冻结源码fbcc0fe、分配来源c923561；完整NATIVE36和TRAIN648均已
通过两级审计后，一次既定训练正常完成，未重试、续训、替换checkpoint或
使用旧188项部分人口。受限OCCAM相关表现参考是标准参考实现，不称完整
原论文复现、A的新机制或CCF A成果。

## 输入、训练与全部费用

训练仅读取648例完整TRAIN的严格公开投影，SHA-256为
{spec['public_sha256']}。
542例有实际窗口，106例无窗口仍保留原分配和抽样权重；三个任务的有窗
轨迹分别push188、reach138、door216。不将3296个相关窗口当独立组；数据
来自18组。真实扰动、噪声、种子、私有状态、旧人口和未来结局未进入模型
输入。归一化只由新TRAIN拟合；没有读Native/CAL/QUAL挑模型。

1000次预训练后，同一状态分叉4000次META和4000次匹配ERM，合计9000次
AdamW更新／尝试、72000次分配轨迹抽取、66712次内层递归更新／Torch求解，
空batch0。全部低于9000／1000000求解／7200秒冻结上限；实际训练
{result['wall_ns']/1e9:.3f}秒，外层受控进程{process['wall_ns']/1e9:.3f}秒。
CPU Python3.12.14／Torch2.2.2+cpu／NumPy1.26.4，float64、单线程确定性。
未更换依赖；训练守卫的物理导入、私有／旧输出读取及网络尝试均0。

训练新增物理交互／在线LLM为0；已有新数据费用684次执行、85789控制步、
34884全部reset、17870945物理帧，实际政策78111次、审计另78111次。
历史v2的27982步／11475全部reset／5877410帧及更早来源另列，完整记录
保留。不能将“训练本身物理0”写成全流程0，也不能隐去旧失败费用。

## 三个预定checkpoint与独立数学检查

PRETRAIN、META_FINAL、MATCHED_ERM_FINAL全部保存原单位／归一化bank和
导出fixtures；未按任何任务成绩选最好checkpoint。原训练入口的status
会覆盖进度，现存最终回执、stdout/stderr和三bank完整保留；没有逐Adam
损失历史，不能据此虚构训练曲线或最优迭代。训练目标是在支持前缀适应后
计算全轨迹窗口MSE，其中可能含支持标签，不称前瞻预测误差。

独立分析在主运行时重算TRAIN归一化，核对Torch／NumPy导出和单位转换，
并用独立批后验核对递归权重。每bank按固定原顺序检查前16条非空TRAIN
轨迹，三bank共918次分析求解，低于5000上限，实际
{audit['wall_ns']/1e9:.3f}秒；新增训练、环境、政策查询和在线LLM均0。

|bank|非空轨迹|最大基函数差|最大预测均值差|最大批／递归后验差|
|---|---:|---:|---:|---:|
{table}

这些16条是TRAIN内数学检查，三个bank共享来源，不是48条独立验证样本。
误差小只证明已声明计算的一致性，不证明模型对机器人有预测能力、区间
已校准、优化稳定、任务收益或安全。全部源文件／bank／回执哈希见
learning_delivery_v1/source_manifest.json，原始记录及失败不变。

## 明确判断与下一阶段

本冻结训练与数学交付通过，可以把三bank固定为后续独立研究输入。
尚未开放科学CAL／QUAL或证明“纠正后适用性”；不能通过TRAIN误差选择
beta、方差尺度、窗口、任务或最终阈值。下一阶段先独立冻结前瞻预测与
实际部署资格的程序、数据权限、组统计、完整费用、失败规则和停止条件。

META适应／冻结、匹配ERM适应／冻结必须在各自实际时序历史上比较；
DIRECT_C8、积分、同历史被动适应、始终获取／不更新、标准完整风险／DR、
简单重加权和既定CPC等强对照继续保留。不能将窗口费用预测更名为完整Q，
也不能用旧行为的离线建议代替新程序执行。A的具体区别应围绕获取／纠正
改变状态和模型适用性建立，而非增加门控、两头网络或标准滤波包装。
若独立资格或完整任务收益失败，封存负结果，不降低基线、筛除困难案例
或用旧QUAL调参。研究贡献、独立任务优势与消融仍未完成，CCF A目标保留。
'''
    (ROOT/'reports/occam_reference_learning_v3_zh.md').write_text(report,encoding='utf8',newline='\n')
    for name in ('report_occam_learning_v3.py','run_occam_training_process_v3.py'):
        shutil.copyfile(Path(__file__).parent/name,OUT/name)
    c.write(OUT/'complete.json',dict(integrity='PASSED_FROZEN_TRAINING_AND_INDEPENDENT_MATHEMATICS_ONLY',
        manifest_id=spec['source_manifest_id'],Adam_updates=9000,training_solves=66712,independent_analysis_solves=918,
        learner_complete_sha256=c.sha(RUN/'learning/complete.json'),model_audit_sha256=c.sha(RUN/'learning/model_audit.json'),
        source_manifest_sha256=c.sha(OUT/'source_manifest.json'),new_physics_during_learning=0,online_LLM_API_calls=0,
        predictive_qualification=False,task_benefit_qualification=False,publication_goal_complete=False))
    print(dict(integrity='PASSED_TRAINING_REPORT',original_files=len(paths),Adam_updates=9000,math_solves=918),flush=True)


if __name__=='__main__':main()
