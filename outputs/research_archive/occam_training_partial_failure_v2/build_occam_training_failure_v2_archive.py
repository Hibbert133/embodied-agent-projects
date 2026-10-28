from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='3759e0e425ddb49e3d199abee1e2c95a494c91e0';parent='ee1162c775c3e54f94b78c9d595ced211c2a5c91'
assert io.git('rev-parse','HEAD')==source
assert io.read(ROOT/'outputs/occam_reference_train_v2/failure_delivery_v2/result_delivery_v1/complete.json')['integrity']=='PASSED_TECHNICAL_FAILURE_DELIVERY_NOT_MODEL_QUALIFICATION'
out=ROOT/'outputs/research_archive/occam_training_partial_failure_v2';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_reader_freeze_v3'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for old,new in (("PARENT='9579f995b81d1010f6e6f6894ef484af8219dad2'","PARENT='"+parent+"'"),
    ("SOURCE='be387b8f073beea835acc85e7b8f98a4b50aec7f'","SOURCE='"+source+"'"),
    ('outputs/research_archive/occam_reference_training_freeze_v2/catalog.json','outputs/research_archive/occam_reader_freeze_v3/catalog.json'),
    ('research_archive_build_occam_reader_v3_20261028_be387b8f073b','research_archive_build_occam_train_failure_v2_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_READER_V3_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_TRAIN_FAILURE_V2_20261028.json'),
    ('Archive complete native records and independently frozen reader-only repair; scientific training and task qualification not complete','Archive closed incomplete training allocation and bounded-stream zero-interaction failure diagnosis')):
    assert old in s,old;s=s.replace(old,new)
replacement='''def scan_all_record_parts():
    specs=(
        ('outputs/occam_window_host/delivery_v1/record_parts_index.json','outputs/occam_window_host/delivery_v1/parts/','outputs/occam_window_host/native_v1/',{'cases.jsonl.gz','events.jsonl.gz','witnesses.jsonl.gz'},3,5),
        ('outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/record_parts_index.json','outputs/occam_reference_train_v2/audit_repair_v3/source_delivery_v1/parts/','outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/native/',{'events.jsonl.gz','witnesses.jsonl.gz'},2,4),
        ('outputs/occam_reference_train_v2/failure_delivery_v2/result_delivery_v1/record_parts_index.json','outputs/occam_reference_train_v2/failure_delivery_v2/result_delivery_v1/parts/','outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/train/',{'events.jsonl.gz','witnesses.jsonl.gz'},2,19))
    restore=OUT/'actual_git_stream_restoration_v1';restore.mkdir(exist_ok=False);allowed=set();checks=[]
    for ordinal,(index_name,part_prefix,original_prefix,basenames,nstream,npart) in enumerate(specs):
        raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','parts index')
        local_allowed=set();local_checks=[];seen=set()
        for artifact in index['artifacts']:
            original=artifact['original_path'];name=Path(original).name
            io.require(original.startswith(original_prefix) and name in basenames and original not in seen,'exact owned original stream');seen.add(original)
            if ordinal:io.require(original==original_prefix+name,'new reference exact original')
            completion_path=(Path(original).parent/'completion.json').as_posix();completion=json.loads(git('show',SOURCE+':'+completion_path))
            io.require(completion['artifact_sha256'][name]==artifact['original_sha256'],'collection completion hash')
            if ordinal==2:io.require(completion['status']=='FAILED_PARTIAL' and completion['manifest_id']=='5c3b6565eee628b32f1ca1eed1b15eb5dc6191b8f47b8293d25efb973a26f510','closed incomplete TRAIN binding')
            recovered=restore/(str(ordinal)+'_'+name);full=hashlib.sha256();total=0
            with recovered.open('xb') as target:
                for part in artifact['parts']:
                    path=part['path'];io.require(path.startswith(part_prefix) and path.endswith('.bin') and path not in allowed and path not in local_allowed,'owned unique part')
                    data=git('show',SOURCE+':'+path);io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git part')
                    target.write(data);full.update(data);total+=len(data);local_allowed.add(path)
            io.require(total==artifact['original_bytes'] and full.hexdigest()==artifact['original_sha256'],'actual complete compressed stream recovery')
            decoded=hashlib.sha256();size=records=0
            with gzip.open(recovered,'rb') as stream:
                for line in stream:
                    decoded.update(line);size+=len(line);records+=1;scan(line,original+'.decoded.json')
            io.require(size==artifact['decoded_bytes'] and decoded.hexdigest()==artifact['decoded_sha256'],'all decoded bytes hash')
            if 'decoded_records' in artifact:io.require(records==artifact['decoded_records'],'decoded record count')
            local_checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(artifact['parts']),decoded_bytes=size,decoded_records=records,decoded_sha256=decoded.hexdigest(),actual_git_recovery_and_every_decoded_row_scanned=True))
        io.require(len(local_checks)==nstream and len(local_allowed)==npart,'complete source index coverage')
        allowed|=local_allowed;checks.append(dict(index_path=index_name,index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=local_checks))
    io.require(len(allowed)==28 and sum(len(q['artifacts']) for q in checks)==7,'all seven streams and28 parts')
    return allowed,dict(strategy='bounded actual Git part to disk; decoded row streaming; no full decoded allocation',indices=checks)


'''
i=s.index('def scan_record_parts():');j=s.index('def main():',i);s=s[:i]+replacement+s[j:]
old="    allowed_parts,record_parts_scan=scan_record_parts()\n    native_parts,native_scan=scan_reader_parts();allowed_parts|=native_parts;record_parts_scan['native_reader_v3']=native_scan"
assert old in s;s=s.replace(old,"    allowed_parts,record_parts_scan=scan_all_record_parts()")
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 最新归档：TRAIN技术停止与零交互失败交付

本地来源{SOURCE}，父归档{PARENT}。NATIVE36完成且审计通过；TRAIN188项
完整，第189项首次见证边界bytes分配失败，459项未启动。所有原分配及预留
关闭，不续接、补齐或用188条绕过648项训练门，未启动任务指标保持null。

原分配实际27982控制步/11475全部reset/5877410物理帧，含失败例51reset/
25500帧/0任务控制步。Windows事件2004支持系统虚拟内存压力；没有内部
完整原生栈，不能指认唯一原因、分配大小或内存泄漏。原事件XML留本地，
去除计算机名/SID的观测与原哈希已保存。没有科学网络训练/在线LLM。

零交互诊断冻结eb0bffc后，逐行核对完整性、闭合、序号/身份/时间和整数
费用；它不是完整政策/PI/执行器重放或完整TRAIN审计，没有训练资格。
8新增检查与2578源码复用共2586唯一，原生/读者失败、全部19实际任务失败、
部分和未启动记录均保留；169/188仅作未平衡前缀的事后描述，无总体收益主张。

新增TRAIN事件/私有见证以19个4MiB上限分片发布。归档器对本轮及历史
共7条流/28分片逐块从实际Git恢复、绑定采集完成哈希，逐行扫描全部解压
字节并核对哈希，不将整条解压大流装入内存。原文件与恢复副本继续保留。

完整中文报告reports/occam_reference_training_partial_failure_v2_zh.md。
下一步先完成资源观测/完整栈/有界生命周期的软件资格；不以弱化见证、调旧
QUAL、复活ARX/SS或换小人口通过。A主线的新获取机制、独立自身历史完整
任务优势、强参考/消融及CCF A目标仍未完成。普通快进，无强推合并或历史删除。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
p=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_reader_freeze_v3','outputs/research_archive/occam_training_partial_failure_v2')
p=p.replace('timeout=50','timeout=300')
(out/'push_archive.py').write_text(p,encoding='utf8',newline='\n');print(source)
