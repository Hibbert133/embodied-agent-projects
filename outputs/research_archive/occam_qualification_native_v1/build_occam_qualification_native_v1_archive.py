"""Archive only complete Native records after actual committed-byte recovery."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis.response_qualification_io_v1 import git
source='1104977105f268baf28b2b53ed1a3f8436c50459';parent='5359d3656dd16fecc27c839b8b378bb8f8cfa8eb'
assert git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_qualification_native_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_behavior_support_v1';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='e41a358311a7d2d33e4be1bc25a60f2853ff6c4d'","PARENT='"+parent+"'"),
    ("SOURCE='d764e27f5a03edef5a5379455df567b298f87cea'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_qualification_freeze_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_behavior_support_v1/catalog.json'"),
    ('research_archive_build_occam_behavior_support_v1_20261028_d764e27f5a03','research_archive_build_occam_qualification_native_v1_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_BEHAVIOR_SUPPORT_V1_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_QUALIFICATION_NATIVE_V1_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
addition=r'''
    qindex_name='outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_index.json'
    qproof_name='outputs/occam_reference_qualification_v1/native_delivery_v1/actual_git_recovery.json'
    qraw=git('show',SOURCE+':'+qindex_name);qindex=json.loads(qraw)
    qproof_raw=git('show',SOURCE+':'+qproof_name);qproof=json.loads(qproof_raw)
    io.require(qraw==(ROOT/qindex_name).read_bytes() and qproof_raw==(ROOT/qproof_name).read_bytes(),'Native qualification exact committed receipts')
    io.require(qindex['schema']=='OCCAM_QUALIFICATION_ZIP_ALIASES_V1' and qindex['phase']=='NATIVE' and qindex['executions']==174
        and len(qindex['files'])==2288 and len(qindex['aliases'])==348,'complete Native qualification record scope')
    io.require(qproof['integrity']=='PASSED_ACTUAL_COMMIT_QUALIFICATION_NATIVE_PARTS_AND_FILES_RESTORATION'
        and qproof['source_commit']=='de7d3541b7af0f24226f141344b3cb4787ba0526'
        and qproof['index_sha256']==hashlib.sha256(qraw).hexdigest() and qproof['result']['files']==2288
        and qproof['result']['all_files_byte_identical'] and qproof['result']['decoded_canonical_gzip_lines']==158286
        and qproof['part_count']==len(qindex['parts'])==12,'Native actual original-byte Git restoration')
    qoids={}
    for part in qindex['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_qualification_v1/native_delivery_v1/bundle_parts/')
            and name.endswith('.bin') and part['bytes']<=4*1024**2,'bounded Native qualification data shard')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==qproof['part_git_oids'][name]==git('rev-parse',qproof['source_commit']+':'+name).decode().strip(),'same actually recovered Native shard object')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'Native shard exact bytes')
        qoids[name]=oid;allowed.add(name)
    portable_name='outputs/occam_reference_qualification_v1/native_delivery_v1/archive_only_restoration.json'
    portable_raw=git('show',SOURCE+':'+portable_name);portable=json.loads(portable_raw)
    io.require(portable_raw==(ROOT/portable_name).read_bytes() and portable['integrity']=='PASSED_ACTUAL_GIT_ARCHIVE_ONLY_NATIVE_RESTORATION'
        and portable['part_git_oids']==qoids and portable['result']['files']==2288
        and portable['result']['size_and_SHA_against_committed_index'] and not portable['result']['original_raw_files_required']
        and not portable['result']['original_raw_byte_comparison'] and not any(portable['guard'].values()),'Native archive-only actual restoration')
    validation_name='outputs/occam_reference_qualification_v1/delivery_tools_v1/archive_only_validation_v1/complete.json'
    validation_raw=git('show',SOURCE+':'+validation_name);validation=json.loads(validation_raw)
    io.require(validation['integrity']=='PASSED_ARCHIVE_ONLY_ENGINEERING_VALIDATION' and validation['unit_tests']==3,'portable engineering checks')
    for name,h in validation['source_sha256'].items():
        io.require(hashlib.sha256(git('show',SOURCE+':'+name)).hexdigest()==h,'tested portable recovery code unchanged')
    records['qualification_native_bundle']=dict(index_path=qindex_name,index_sha256=hashlib.sha256(qraw).hexdigest(),
        proof_path=qproof_name,proof_sha256=hashlib.sha256(qproof_raw).hexdigest(),data_commit=qproof['source_commit'],
        actual_part_git_oids=qoids,files=2288,parts=12,exact_gzip_aliases=348,decoded_canonical_gzip_lines=158286,
        portable_proof_path=portable_name,portable_proof_sha256=hashlib.sha256(portable_raw).hexdigest(),
        portable_source_raw_read_attempts=0,portable_original_comparison_not_claimed=True,
        no_new_science_or_recovery_during_archive=True)
    io.require(len(allowed)==133,'exact historical and Native bounded lossless part scope')
'''
needle='    return allowed,records';assert s.count(needle)==1;s=s.replace(needle,addition+'\n'+needle)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 独立自身历史参考：完整NATIVE174无损数据交付

来源{SOURCE}，父归档{PARENT}。29真实程序×三任务×两条件＝174完整执行，
两级审计通过，173任务成功／1任务失败／0技术失败。单独只有一个独立组，
不能把该运行门当成独立预测／任务优势、A新获取机制或CCF A成果。

实际14894控制步、8874全部reset、4511470物理帧；固定策略13104查询，
学习参考274窗口／102实际后验更新，原C4/C8计24估计及nfev24。审计求解／
拟合单列，历史TRAIN／C8／旧失败费用保留。在线LLM始终0。

2288原文件、348精确gzip成员别名、12个<=4MiB分片，47099700字节ZIP。
本地ZIP与实际Git分片均逐文件对原件恢复成功；另在禁止读取原科学目录
条件下，独立于原件按索引恢复所有文件，实际读取尝试0。158286行规范
gzip秘密扫描通过；别名重用规范流解码扫描，不虚报重复扫描次数。
归档重新核对分片Git对象／SHA与实际恢复证明，不新采集或复原。恢复入口
支持精简归档的实际包含提交，不要求原件；完整新clone依赖安装未实测。

13原导出工程检查＋3归档独立恢复检查通过，四归档算法AST与旧实现相同，
仅格式字符串规范化。封存编码别名错误及未完成预回执、源码均保留。原
原始记录、大ZIP、所有恢复副本和失败继续保留。源代码／模型／科学参数
未改；仍运行的QUAL不在本归档，不能由NATIVE表调参或取表现最佳程序。
后续完整九独立组QUAL、强主比较、独立统计与负结果交付仍待完成。
当前源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；
省略数据有完整大小／SHA目录，保留全部133个经个别证明的记录分片。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive complete TRAIN behavior-support audit without new interactions or off-policy value claims','Archive complete audited own-history Native174 records with actual Git and archive-only restorations')
s=s.replace('allow individually proved old, Native and complete TRAIN lossless parts','allow individually proved old, Native, complete TRAIN and qualification Native174 lossless parts')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_behavior_support_v1','outputs/research_archive/occam_qualification_native_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)
