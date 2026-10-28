from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='be387b8f073beea835acc85e7b8f98a4b50aec7f';parent='9579f995b81d1010f6e6f6894ef484af8219dad2'
assert io.git('rev-parse','HEAD')==source
assert io.read(ROOT/'outputs/occam_reference_train_v2/audit_repair_v3/freeze_validation_v1/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/occam_reader_freeze_v3';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_reference_training_freeze_v2'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for old,new in (("PARENT='f54d2dae7433e64dae6f97a67a3a499618d0fd20'","PARENT='"+parent+"'"),
    ("SOURCE='a60c1d8bb5ae3542baf6f9c72f44cadab23cf375'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_reference_training_failure_v1/catalog.json','outputs/research_archive/occam_reference_training_freeze_v2/catalog.json'),
    ('research_archive_build_occam_train_freeze_v2_20261028_a60c1d8bb5ae','research_archive_build_occam_reader_v3_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FREEZE_V2_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_READER_V3_20261028.json'),
    ('Archive v2 repaired collector and frozen independent standard-reference training; no new physical collection yet','Archive complete native records and independently frozen reader-only repair; scientific training and task qualification not complete')):
    assert old in s,old;s=s.replace(old,new)
addition='''
def scan_reader_parts():
    index_name='outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/record_parts_index.json'
    raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','reader source parts index')
    prefix='outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/native/'
    completion=json.loads(git('show',SOURCE+':'+prefix+'completion.json'))
    manifest=json.loads(git('show',SOURCE+':'+prefix.removesuffix('native/')+'manifest.json'))
    io.require(completion['manifest_id']==manifest['manifest_id']=='5c3b6565eee628b32f1ca1eed1b15eb5dc6191b8f47b8293d25efb973a26f510','original native identity')
    allowed=set();checks=[];seen=set()
    for artifact in index['artifacts']:
        original=artifact['original_path'];name=Path(original).name
        io.require(original==prefix+name and name in ('events.jsonl.gz','witnesses.jsonl.gz') and name not in seen,'exact original native stream')
        seen.add(name);io.require(artifact['original_sha256']==artifact['completion_sha256']==completion['artifact_sha256'][name],'collection completion binding')
        values=[]
        for part in artifact['parts']:
            path=part['path'];io.require(path.startswith('outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/parts/') and path.endswith('.bin') and path not in allowed,'owned bounded reader part')
            data=git('show',SOURCE+':'+path)
            io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git reader part')
            values.append(data);allowed.add(path)
        joined=b''.join(values);decoded=gzip.decompress(joined)
        io.require(len(joined)==artifact['original_bytes'] and hashlib.sha256(joined).hexdigest()==artifact['original_sha256'],'actual full reader stream recovery')
        io.require(len(decoded)==artifact['decoded_bytes'] and hashlib.sha256(decoded).hexdigest()==artifact['decoded_sha256'],'actual decoded reader stream')
        scan(decoded,original+'.decoded.json')
        checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(values),decoded_bytes=len(decoded),decoded_sha256=artifact['decoded_sha256'],actual_git_recovery_and_full_decoded_scan=True))
    io.require(len(checks)==2 and len(allowed)==4,'all native reader streams and four parts')
    return allowed,dict(index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=checks)

'''
i=s.index('\ndef main():');s=s[:i]+'\n'+addition+s[i:]
old='    allowed_parts,record_parts_scan=scan_record_parts()'
new=old+"\n    native_parts,native_scan=scan_reader_parts();allowed_parts|=native_parts;record_parts_scan['native_reader_v3']=native_scan"
assert old in s;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 最新归档：真实原生数据及只读读者修复v3冻结

本地来源{SOURCE}，父归档{PARENT}。原生36次实际执行、3111控制步、1836次
全部reset和933555物理帧已完成，原读者在旧命名空间常量断言处失败。
原错误日志、守卫、51字节部分公开导出与原FAILED_PARTIAL流水线全部保留。

修复版本只把噪声编号断言绑定既有冻结登记，并隔离新的NATIVE导出；完整噪声
哈希、逐步执行/成本/见证及全部人口要求保留。7新增与5重复路径回归分别计数，
2571项源码复用，共2578唯一。没有修复导致的新物理/拟合/优化/API。
首例保存记录与错误编号/哈希、噪声移位、未来历史均由数组测试覆盖。

大事件和私有见证以四个4MiB上限分片发布，归档器实际从Git取回并恢复两个
完整压缩流，核对原采集完成哈希并完整解压秘密扫描；原文件与恢复副本留本地。
当前源提交包含新读者与未启动TRAIN的受控续接冻结；源提交之后运行中的
原生重审、TRAIN及后续训练结果不在此快照，不把它写成科学资格已经完成。

见reports/occam_reference_train_reader_v3_freeze_zh.md。科学CAL/QUAL、新获取
机制、强对照完整任务收益、消融及CCF A目标尚未完成。全程零在线LLM；
保留全部旧失败/负结果、来源与省略目录。普通快进，无强推合并或历史删除。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_reference_training_freeze_v2','outputs/research_archive/occam_reader_freeze_v3')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source)
