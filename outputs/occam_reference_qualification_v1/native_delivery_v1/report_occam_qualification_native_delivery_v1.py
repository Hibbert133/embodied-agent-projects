"""Report the complete operational Native population; do not read QUAL outcomes."""
from pathlib import Path
import csv,json,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'
OUT=b.c.BASE/'native_delivery_v1'


def main():
    m,s,p,a=b.ready(RUN/'manifest.json','NATIVE');index=b.c.read(OUT/'bundle_index.json');restore=b.c.read(OUT/'local_restoration.json')
    assert restore['all_files_byte_identical'] and restore['files']==len(index['files'])==2288
    guard=b.c.read(OUT/'guard.json');assert not any(guard['counts'].values())
    names=list(dict.fromkeys(r['program'] for r in m['config']['populations']['NATIVE']));assert len(names)==29
    programs=[];failures=[]
    for name in names:
        rows=[r for r in s['rows'] if r['program']==name];assert len(rows)==6
        programs.append(dict(program=name,executions=len(rows),successes=sum(r['success'] for r in rows),
            mean_deadline_loss=sum(r['deadline_loss'] for r in rows)/len(rows),actual_control_steps=sum(r['total_steps'] for r in rows)))
    for i,row in enumerate(s['rows'],1):
        if not row['success']:failures.append(dict(case_index=i,**row))
    with (OUT/'all_cases.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['case_index',*s['rows'][0]]);writer.writeheader()
        for i,row in enumerate(s['rows'],1):writer.writerow(dict(case_index=i,**row))
    with (OUT/'task_failures.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['case_index',*s['rows'][0]]);writer.writeheader();writer.writerows(failures)
    b.c.write(OUT/'operational_summary.json',dict(scope='COMPLETE_NATIVE_OPERATIONAL_GATE_ONLY',executions=174,
        task_successes=173,task_failures=len(failures),technical_failures=0,independent_groups=1,programs=programs,
        control_steps=s['control_steps'],ledger=s['lifecycle'],audit_counts=a['counts'],
        predictions_or_task_superiority_qualified=False,all_QUAL_results_used=False,online_LLM_API_calls=0))
    rows=s['rows'];trained=[r for r in rows if r['program'].startswith(('META_','ERM_'))]
    updates=sum(r['full_feedback_windows'] for r in rows)
    costs=s['lifecycle']['counts'];lines=['# 独立自身历史资格：NATIVE 完整交付（中文）','',
        '174/174 次原生执行完成，两级审计均通过，29 个程序均按冻结分配实际执行。NATIVE 只有 1 个独立组，本报告是运行与数值链路交付，不构成预测、任务收益或 CCF A 资格；QUAL 使用另 9 个组，本报告不读取其结局。','',
        f"全部人口为 173 个任务成功、{len(failures)} 个任务失败、0 技术失败；失败仍在分母与原始记录中。共有 {a['counts']['observed_windows']} 个实际窗口。下面均为描述性结果，没有独立组置信区间、方法选择或择优获取动作。",'',
        '|冻结程序|成功／6|平均截止损失↓|实际控制步|','|---|---:|---:|---:|']
    for row in programs:lines.append(f"|{row['program']}|{row['successes']}/6|{row['mean_deadline_loss']:.3f}|{row['actual_control_steps']}|")
    lines+=['','PI 的数字是积分纠正的时间常数 T（秒），小 T 反馈更快；META 是元训练的短窗表现预测参考，ERM 是同数据、匹配训练量的普通监督参考；ADAPT 用实际窗口反馈更新线性后验，FROZEN 保持后验参数。底层策略固定。后缀 CONTINUE／VALIDATE8／MOVE_MEASURE 分别为继续、执行 8 步正常任务验证、真实移动后测量。','',
        '同前缀程序先以 T=0.5 到预定边界；GLOBAL 从第 0 步就使用该时间常数。GLOBAL_PI_0500 是 PI_0500__CONTINUE 的精确别名，未重复执行或计费。DIRECT_C8／MOVE_INTEGRAL 保持原冻结强参考及其初始探测、估计和获取过程。不同前缀不得伪称共同移动／当前状态。','',
        f"实际费用：{s['control_steps']} 控制步；174 次受控重置，{costs['reset_attempts']} 次全部重置（含 8,700 次目标生成重置）；{costs['simulation_frames_attempted']} 物理帧。实际固定策略查询 {sum(r['policy_queries'] for r in rows)}，学习参考实际窗口 {sum(r['performance_windows'] for r in trained)}，实际后验更新 {updates}。原 C4/C8 数值估计 {a['counts']['actual_c4_c8_fit_attempts']} 次／优化器报告 nfev={a['counts']['actual_c4_c8_optimizer_nfev']}。新神经／响应训练及在线 LLM API 均为 0。",'',
        '审计费用另计：'+json.dumps(a['guard']['operation_counts'],ensure_ascii=False)+'。审计没有创建、重置或推进环境；共享 actor／固定策略／严格特征抽取已披露，独立标量滤波、批后验、dense 算术与动作／噪声／连续性重建不等于独立物理重仿真。','',
        '来源训练、全部失败的旧人口与 C8 离线来源费用沿用冻结 historical_source_costs.json，单独报告，不按当前程序数重复乘计。历史 TRAIN 的元／ERM 训练资格和数学审计不是本 NATIVE 的任务表现证据。','',
        f"无损交付：{len(index['files'])} 个原始文件，{len(index['aliases'])} 个逐案压缩成员以精确字节区间引用完整事件／见证流；{len(index['parts'])} 个不超过 4 MiB 的分片，ZIP 共 {index['bundle_bytes']} 字节。实际本地恢复逐文件字节一致，{restore['decoded_canonical_gzip_lines']} 行规范 gzip 内容经基本及补充秘密扫描；别名不重复解码扫描、不重复计环境费用。原始数据、ZIP 及恢复目录继续保留。实际 Git 分片恢复证明在数据提交后另存。",'',
        'all_cases.csv 保留全部 174；task_failures.csv 保留全部任务失败。bundle_index.json 给出所有原文件大小、SHA-256、分片与压缩成员映射。导出软件 13 项文件／元数据检查通过，4 个归档／恢复算法与已验证实现的 AST 相同，仅格式版本字符串规范化；它们不是新增科学资格。导出本身环境交互、拟合、模型预测及在线 LLM 全 0。','',
        '后续判断保持冻结：继续同一 QUAL 分配，完整收集后双审计、独立整组统计与全部对照交付；不根据本表更换主程序、bank、阈值、获取动作或样本。无收益保留负结果，封存该版接收者。A 的新机制、完整 Q／DR／廉价重加权等强参考、独立完整任务优势和消融仍待完成。','',
        '科学冻结源码：'+m['source_git_commit']+'；manifest '+m['manifest_id']+'。','']
    text='\n'.join(lines)
    with (ROOT/'reports/occam_reference_qualification_native_v1_zh.md').open('x',encoding='utf8',newline='\n') as f:f.write(text)
    with (OUT/'report_zh.md').open('x',encoding='utf8',newline='\n') as f:f.write(text)
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    b.c.write(OUT/'delivery_sources.json',dict(manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],
        phase='NATIVE',source_files=index['files'],bundle_index_sha256=b.c.sha(OUT/'bundle_index.json'),
        software_freeze_sha256=b.c.sha(b.c.BASE/'delivery_tools_v1/validation_v1/complete.json'),
        audit_sha256=b.c.sha(RUN/'native/audit.json'),process_audit_sha256=b.c.sha(RUN/'native/process_audit.json'),
        all_QUAL_results_used=False,new_physics=0,new_fits=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED_COMPLETE_NATIVE_OPERATIONAL_REPORT',programs=29,executions=174,task_failures=len(failures)),flush=True)


if __name__=='__main__':main()
