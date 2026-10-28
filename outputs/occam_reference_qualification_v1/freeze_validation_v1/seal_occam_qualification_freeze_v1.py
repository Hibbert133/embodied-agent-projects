"""Stage only the completed tested qualification implementation, never collect."""
from pathlib import Path
from time import perf_counter_ns
import gzip,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis import occam_qualification_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    started=perf_counter_ns();out=a.VALIDATION;v=c.read(out/'validation_receipt.json')
    assert v['integrity']=='PASSED_FORMAL_ARRAY_RUNTIME_COMPILE_DEPENDENCIES' and v['actual_formal_tests']==34
    assert v['main_pip_check_exitcode']==0 and v['real_process_launch_attempts']==0 and not any(v['guard']['operation_counts'][k] for k in ('environment_creations','resets','simulation','cold_fit_attempts'))
    assert git('rev-parse','HEAD').decode().strip()=='4dafbb17e04f33df8d38f4270e0b7246dff8072e'
    assert not git('diff','--name-only').strip() and not git('diff','--cached','--name-only').strip()
    assert not list(a.OUTPUT.glob('*/manifest.json'))
    reuse=c.read(out/'source_reuse.json')
    for name,h in {**v['source_sha256'],**v['input_sha256'],**reuse['source_sha256']}.items():assert c.sha(ROOT/name)==h,name
    for name in ('seal_occam_qualification_freeze_v1.py','run_occam_qualification_pipeline_v1.py','complete_occam_fixed_reference_review_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
    cost_report='reports/cold_start_evidence_qualification_v1.md'
    c.write(out/'historical_source_costs.json',dict(integrity='PASSED_SOURCE_BOUND_COST_DISCLOSURE',
        trained_performance_banks=dict(executions=684,control_steps=85789,controlled_resets=684,all_resets=34884,physical_frames=17870945,
            actual_joint_AdamW_updates=9000,per_method_standalone_AdamW_updates=5000,shared_pretrain_updates=1000,
            training_solves=66712,mathematical_audit_solves=918,source_report='reports/occam_reference_learning_v3_zh.md'),
        closed_v2_partial_source=dict(control_steps=27982,all_resets=11475,physical_frames=5877410,not_training_input=True),
        C8_nominal_training=dict(control_steps=3072,controlled_resets=384,all_resets=19584,physical_frames=9807360,charged_to_legacy_C8_users_only=True),
        C8_complete_source_study_including_training_not_additive=dict(control_steps=3840,controlled_resets=480,all_resets=24480,physical_frames=12259200,
            source_report=cost_report,source_report_sha256=c.sha(ROOT/cost_report)),
        older_history_trace=dict(old_ARX_control_steps=21010,old_ARX_controlled_resets=288,old_ARX_not_current_model_input=True,
            older_legacy_control_steps=2304,older_legacy_offline_resets=144,full_lifecycle_unknown_not_zero=True),
        historical_qualification_fees_separate=True,no_duplicate_source_cost_per_program=True,new_physics=0,online_LLM_API_calls=0))
    report=f'''# 固定表现参考独立资格：实现冻结 v1

2026-10-28。本次交付收集器、严格公开提供器、完整连续主机、两级记录审计、
独立标量／批后验、分组统计与独立复算及中文报告入口。未创建科学分配，
没有新环境、重置、控制步、真实worker、模型重训或在线LLM API。

最终34项纯数组／假句柄／保存记录检查通过；旧2661项按源码哈希复用，
合计2695项不同检查，不能把重复执行或构造轨迹计为新科学样本。
全仓compileall、主运行时锁和pip check通过；既定训练运行时的来源回执
复用，未安装依赖。最后正式检查14秒量级，精确墙时见validation_receipt。
数组模型更新／求解是构造检查，已单列守卫次数，不作真实训练或任务结果。

首次28项中一项AST比较因版本结果schema名称不同而失败，原快照／日志保留。
早期30／32项正式通过和源码快照也保留，不宣称最终版本沿用了不同源码
的全部验收。最终AST只归一化结果schema与训练费用字段名称，超时、终止、
单句柄与一次启动逻辑保持。NATIVE要求实际模型使用；QUAL提前成功没有
窗口时保留null与全分母，不误作执行错误。最后预算余段按事前声明长度
判断完整性，不补成16步；冻结模式从不更新参数。

完整原要求还包括全时固定四T，因此在24个同前缀程序和DIRECT_C8／
MOVE_INTEGRAL之外加入三条从0步开始的固定控制。全时0.5秒与已有程序
严格等同，按别名引用一次。最终29个真实程序，NATIVE174后一次QUAL1566，
共1740执行、870000控制步、88740全部reset、48720000帧上限；原C4/C8
最多240估计、递归更新11160，审计预算单列。所有29程序／三任务／两条件／
三时点完整保留；不在结果后扩样或选择最佳获取臂。主META_CONTINUE须在
完整54单元中同时通过十个预定强参考的95%截止损失差上界<0，成功变化
另报；预测与数值资格分开，不以一个替代另一个。

新种子范围已由两个解析器核对664个来源，无登记冲突；正式创建manifest
前还会复核完整登记。资源快照达到4GiB提交／磁盘门，但不预留或保证未来
资源，实际每例继续210秒及活跃资源门；失败关闭分配，无重试、续接或
旧数据填充。所有历史费用见historical_source_costs，C8完整研究包括其
训练费用，两者不可相加；不把旧ARX缺少全生命周期账本记成零。

三bank和匹配ERM来源冻结，不再选模型或训练。每个部署程序自己选择并
执行增益、从自己的真实事实反馈更新。冻结／适应因素、未来查询拒绝、
保存命令实际消费、噪声游标与裁剪顺序、所有分组及缺失已覆盖。实际模型
输出尚未在新机器人任务中验证，旧保存记录只用于机械读者检查，不晋级
为新方法执行。OCCAM与模型适用域已有相邻机制，本次只是标准参考资格。

下一步：本地提交冻结，按同一版本创建一次分配、NATIVE完整双审计后再
QUAL与独立统计。无收益则保留负结果、停止围绕此版接收者叠加选择规则。
A的具体获取／采用机制、完整Q／DR与廉价重加权等强参考、独立任务收益和
消融仍需后续证据，CCF A目标未完成。
'''
    (ROOT/'reports/occam_reference_qualification_freeze_v1_zh.md').write_text(report,encoding='utf8',newline='\n')
    source=dict(v['source_sha256']);source.update({(out/name).relative_to(ROOT).as_posix():c.sha(out/name) for name in
        ('run_occam_qualification_pipeline_v1.py',)})
    inputs=dict(v['input_sha256']);inputs[(out/'source_reuse.json').relative_to(ROOT).as_posix()]=c.sha(out/'source_reuse.json')
    inputs[(out/'historical_source_costs.json').relative_to(ROOT).as_posix()]=c.sha(out/'historical_source_costs.json')
    c.write(out/'complete.json',dict(integrity='PASSED',scope='FROZEN_STANDARD_REFERENCE_OWN_HISTORY_SOFTWARE_ONLY',source_sha256=source,input_sha256=inputs,
        validation_receipt_sha256=c.sha(out/'validation_receipt.json'),new_unique_tests=34,reused_unique_tests=2661,unique_tests=2695,
        actual_final_formal_tests=34,earlier_formal_test_executions=94,development_test_executions=58,
        process_body_metadata_only_versioning=True,new_environment_interactions=0,actual_native_workers=0,
        new_neural_or_response_training=0,online_LLM_API_calls=0,scientific_allocation_created=False,publication_goal_complete=False,
        seal_wall_ns=perf_counter_ns()-started))
    owned=set(source)|{'reports/occam_reference_qualification_freeze_v1_zh.md'}
    owned|={p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if name.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(r.search(text) for r in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');c.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_and_decoded_scan=True,
        full_tracked_scan_reused_from_checked4dafbb1_chain=True,unrelated_untracked_files_excluded=True))
    owned.add((out/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_FROZEN_QUALIFICATION_IMPLEMENTATION',owned_files=len(owned),unique_tests=2695,new_tests=34,allocation_created=False),flush=True)


if __name__=='__main__':main()
