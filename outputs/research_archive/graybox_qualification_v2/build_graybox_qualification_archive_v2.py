"""Build a compact archive from a completed, checked supplemental result commit."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import graybox_qualification_io_v2 as a
io=a.io;path=Path(sys.argv[1]).resolve();root=path.parent;source=io.git('rev-parse','HEAD');parent='db378040920c006e37c118576d5f9226c36f86d4'
assert io.read(a.BASE/'result_validation_v2/complete.json')['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no')
decision=io.read(root/'presentation/research_decision.json');cost=io.read(root/'presentation/costs.json');qual=decision['qualification'];lock=io.read(root/'model_lock.json') if (root/'model_lock.json').exists() else None
out=ROOT/'outputs/research_archive/graybox_qualification_v2';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/graybox_result_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='1cae03ce34ec373675d02c1afb2d47c55697f6e3'","PARENT='"+parent+"'"),
    ("SOURCE='e784794ded175d35de5dea19a2ca756a68e35fe7'","SOURCE='"+source+"'"),
    ('outputs/research_archive/graybox_freeze_v1/catalog.json','outputs/research_archive/graybox_result_v1/catalog.json'),
    ('research_archive_build_graybox_result_20261028_e784794ded17','research_archive_build_graybox_qualification_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_GRAYBOX_RESULT_20261028.json','ARCHIVE_FILE_CATALOG_GRAYBOX_QUALIFICATION_20261028.json'),
    ('Archive graybox failed pre-qualification run and read-only audit repair; no model superiority claim','Archive independent graybox qualification supplement; zero new primary fits or online LLM')):
    assert old in s,old;s=s.replace(old,new)
old="or name=='outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz':data=gzip.decompress(data)"
assert old in s;s=s.replace(old,"or name in ('outputs/graybox_response/freeze_validation_v1/seed_scope.json.gz','outputs/graybox_qualification/freeze_validation_v2/ownership_scope.json.gz'):data=gzip.decompress(data)")
headline='未产生独立QUAL结论。' if qual is None else '\n'.join(n+': '+format(v*1000,'.9f')+' mm full-allocation endpoint loss' for n,v in qual['full_allocation_mean_m'].items())
note=f'''# 最新归档：标准灰箱响应参考的独立资格补充

来源本地 {source}，冻结168d239，父归档 {parent}。
状态 {decision['status']}。原训练审计技术失败、459条来源及只读修复保持。
本补充仅执行原预留但未用的CAL/QUAL分配，未重采训练人口、换种子或拟合模型。
模型SHA固定{a.MODEL_SHA}；q锁定值{None if lock is None else lock['selected_q']}。

{headline}

新费用：{cost['new_total']}。
含原真实来源的累计费用：{cost['combined_actual']}。
完整病例、缺失、失败、全部五参考区间/任务/时域门和分层见中文报告
reports/graybox_qualification_v2_zh.md。原未启动占位条目不重复计为执行。
这是已声明命令包上的标准输入差响应组件，不能称为绝对状态/参数/逆控制、
完整任务收益、安全或新获取算法。CCF A目标仍未完成。

18项新增、2410项旧源码绑定复用，共2428项唯一检查；编译、依赖、全跟踪
秘密扫描、新实际索引BASIC/EXTRA与差异/字节检查通过。Windows短路径开发
失败及修正保留。原所有科学负结果和故障均保留，零在线LLM API，零新主拟合。
原始大记录、分片及实际恢复副本均在本地保留；远端省略项按完整目录披露。
补充查新保留局部有效性主动学习和PDML等直接先例，不将重加权/误差门称新颖。
'''
i=s.index("    note=f'''");j=s.index('    extras={',i)
tail="""\n完整源树{len(catalog)}项，发布{sum(r['published'] for r in catalog)}项；沿原规则省略
原始jsonl.gz、.bin分片和>8MiB文件，逐项SHA、大小、发布状态见
ARCHIVE_FILE_CATALOG_GRAYBOX_QUALIFICATION_20261028.json，不声称全部大数据在远端。
普通快进，无强推、合并或删除历史；归档不计科学贡献。
"""
# The source note contains only controlled identifiers/numbers and static prose.
note=note.replace('{','{{').replace('}','}}');s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/graybox_result_v1/push_graybox_result_archive_v1.py').read_text('utf8').replace('outputs/research_archive/graybox_result_v1','outputs/research_archive/graybox_qualification_v2')
(out/'push_graybox_qualification_archive_v2.py').write_bytes(p.encode('utf8'));print(source)
