"""Seal the complete source-only receiver analysis without re-running inference."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_receiver_prefix_support_v1';sys.path.insert(0,str(BASE/'tools'))
import run_prefix_support_v1 as r
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=BASE/'delivery_v1';SOURCE='dc26138757337c79c55b38bd4dfb742c5e62dae8'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    complete=r.read(BASE/'analysis_v1/complete.json');assert complete['integrity']=='PASSED_COMPLETE_IN_SAMPLE_RECEIVER_PREFIX_AUDIT'
    for n,h in complete['artifact_sha256'].items():assert r.sha(ROOT/n)==h,n
    f=r.read(r.FREEZE)
    for section in ('source_sha256','input_sha256','component_sha256'):r.verify(f[section])
    q=r.read(r.QMANIFEST);r.verify(q['source_sha256'])
    counts=r.read(BASE/'cost_reconstruction.json');assert counts['main_declarations']==3027 and counts['main_symmetric_eigendecompositions']==44148
    assert counts['wall_budget_passed'] and complete['wall_ns']<=1800*10**9
    audit=r.read(BASE/'analysis_v1/audit.json');assert audit['main_models_replay_and_statistics_disabled'] and audit['receiver_analyses']==2592
    assert not any(r.read(BASE/'analysis_v1/guard.json')['counts'].values())
    for row in r.rows(BASE/'analysis_v1/trajectories.jsonl'):
        assert row['value']['target_task_loss'] is None and row['value']['target_task_success'] is None
    for part in r.read(BASE/'analysis_v1/decision_parts.json')['parts']:
        p=BASE/'analysis_v1'/part['path'];assert p.stat().st_size==part['bytes']<=4*1024**2 and r.sha(p)==part['sha256']
    OUT.mkdir(exist_ok=False);shutil.copyfile(__file__,OUT/Path(__file__).name)
    source_proof=Path(__file__).parent/'occam_core_postcommit_dc2613875733.json';assert r.read(source_proof)['commit']==SOURCE
    shutil.copyfile(source_proof,OUT/'frozen_committed_bytes.json')
    note='''# 接收者前缀支持：完整交付与费用说明

完整原报告见 [事后描述性报告](occam_receiver_prefix_support_v1_zh.md)。
648来源×4接收者＝2592份分析、432分层、18独立组全部完成，独立数值／
记录／统计复算通过。没有接收者部署或新物理轨迹；任务结果字段均缺失。

对每个接收者的542条非空来源：META_ADAPT／FROZEN各493条首次增益分歧、
49条全部观测增益相同；ERM两程序各484条首次分歧、58条全相同。每种
接收者另有106条无决定记录。比例不能解释为任务效果或统计覆盖；bank
训练使用同一来源，不能当独立前瞻评价。当前QUAL及全部主比较没有改变。

主分析3027声明／12108候选预测、440分析端递归更新／线性求解、44148
对称特征分解；独立复算同样3027声明对应基函数／12108候选及440标量
更新，0线性求解。成本可由2168先验会话、1073匹配反馈、1954首次分歧
及冻结代码独立重建：eig=3×2168+12×3027+3×440。全阶段1790.990秒，
低于冻结1800秒；不重复运行分析。20项新合成检查通过，开发20次和正式
20次执行分开记；旧科学编译／依赖回执按未变源码复用。

额外费用必须单列：运行中做过两次使用冻结META bank的合成输入计时，
共2声明／8候选、0后验更新／求解；30次eig由成功代码分支复算，未直接
作为运行计数剖析。计时含cProfile，两个进程与主分析墙钟重叠，不能相加
冒充串行耗时或实时机器人资格。命令控制台记录之后写入receipt，复现
入口不覆盖原收据。它们没有读取额外TRAIN轨迹或推进环境。

新增环境／全部reset／帧／固定政策查询／神经训练／批量拟合／seed／
在线LLM全0。原来源费用及失败继续保留；不能用“零交互”省略上述模型
运算。cost_reconstruction.json和reconstruct_cost_v1.py提供复算；两次
辅助计时在runtime_diagnostic_v1/receipt.json单列。

首次分歧之后的旧反馈没有提交给接收者。全匹配也不自动证明所有发送
命令或隐状态相同，更不成为任务结局；本次不生成完整Q／DR监督标签。
完整风险强参考、独立自身历史任务收益、新获取机制及消融仍待证明。
首窗口全候选诊断只是DESIGN_ONLY，待原完整QUAL与统计完整性通过后
另冻reader，不读运行前缀或挽救失败门。CCF A目标仍未完成。
'''
    with (ROOT/'reports/occam_receiver_prefix_support_v1_delivery_zh.md').open('x',encoding='utf8',newline='\n') as out:out.write(note)
    with (OUT/'report_zh.md').open('x',encoding='utf8',newline='\n') as out:out.write(note)
    r.write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_RECEIVER_PREFIX_ANALYSIS_DELIVERY',frozen_source_commit=SOURCE,
        main_complete_sha256=r.sha(BASE/'analysis_v1/complete.json'),cost_reconstruction_sha256=r.sha(BASE/'cost_reconstruction.json'),
        auxiliary_runtime_receipt_sha256=r.sha(BASE/'runtime_diagnostic_v1/receipt.json'),source_cases=648,analyses=2592,cells=432,
        declarations=3027,main_candidate_predictions=12108,main_analysis_updates=440,main_solves=440,main_eigen=44148,
        auxiliary_synthetic_declarations=2,auxiliary_candidate_predictions=8,auxiliary_code_reconstructed_eigen=30,
        new_array_tests=20,old_scientific_source_files_verified_unchanged=len(q['source_sha256']),
        current_QUAL_outcomes_used=False,new_environment_interactions=0,new_neural_training_or_batch_fits=0,online_LLM_API_calls=0,
        in_sample_only_no_value_or_deployment_claim=True,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'reports/occam_receiver_prefix_support_v1_zh.md','reports/occam_receiver_prefix_support_v1_delivery_zh.md',
        'docs/research/occam_first_window_diagnostic_design_v1_zh.md','docs/research/correction_scope_contribution_review_v7_addendum_zh.md'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.py'):compile(data,n,'exec')
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',sha256=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_PREFIX_RESULTS_STAGED',changed_files=len(git('diff','--cached','--name-only').splitlines()),source_cases=648,analyses=2592),flush=True)


if __name__=='__main__':main()
