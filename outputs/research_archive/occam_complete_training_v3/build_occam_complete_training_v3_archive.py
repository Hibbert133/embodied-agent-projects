"""Prepare bounded archival code for complete training and lossless full TRAIN data."""
from pathlib import Path
import argparse,re,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io


def main(source):
    assert re.fullmatch('[0-9a-f]{40}',source) and io.git('rev-parse','HEAD')==source
    parent='92192604a91a5ccd17b22412d7a8c1cca2dcddc5'
    out=ROOT/'outputs/research_archive/occam_complete_training_v3';out.mkdir(exist_ok=False)
    template=ROOT/'outputs/research_archive/occam_qualification_review_v1'
    s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
    pairs=(("PARENT='16de5ce6fe97e25240ac34be6b3585d4fe71740e'","PARENT='"+parent+"'"),
        ("SOURCE='d6b38a11d5ccc6c4f253feb4b0a85fd5f7f2683f'","SOURCE='"+source+"'"),
        ("baseline_path=ROOT/'outputs/research_archive/occam_native_stage_log_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_qualification_review_v1/catalog.json'"),
        ('research_archive_build_occam_qual_review_v1_20261028_d6b38a11d5cc','research_archive_build_occam_complete_training_v3_20261028_'+source[:12]),
        ('ARCHIVE_FILE_CATALOG_OCCAM_QUAL_REVIEW_V1_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_COMPLETE_TRAINING_V3_20261028.json'),
        ('    return allowed,dict(strategy=','    records=dict(strategy='))
    for before,after in pairs:assert before in s,before;s=s.replace(before,after)
    extra='''    train_index_name='outputs/occam_reference_train_v3/train_delivery_v1/bundle_index.json'
    train_proof_name='outputs/occam_reference_train_v3/train_delivery_v1/actual_git_recovery.json'
    train_raw=git('show',SOURCE+':'+train_index_name);train=json.loads(train_raw)
    proof_raw=git('show',SOURCE+':'+train_proof_name);proof=json.loads(proof_raw)
    io.require(train_raw==(ROOT/train_index_name).read_bytes() and proof_raw==(ROOT/train_proof_name).read_bytes(),'TRAIN exact committed proof bytes')
    io.require(train['schema']=='OCCAM_TRAIN_ZIP_ALIASES_V1' and proof['integrity']=='PASSED_ACTUAL_COMMIT_TRAIN_PARTS_AND_FILES_RESTORATION'
        and proof['source_commit']=='634b3454fa0dd3aceb901ba565be2d80b854ec40'
        and proof['index_sha256']==hashlib.sha256(train_raw).hexdigest()
        and proof['result']['files']==len(train['files'])==8450 and proof['part_count']==len(train['parts'])==83
        and proof['result']['reconstructed_member_files']==len(train['aliases'])==1296
        and proof['result']['decoded_canonical_gzip_lines']==802542 and proof['result']['all_files_byte_identical'],'all648 original TRAIN files restored and decoded-scanned')
    io.require(git('rev-parse',SOURCE+':'+train_index_name)==git('rev-parse',proof['source_commit']+':'+train_index_name),'same actually recovered TRAIN index')
    train_oids={}
    for part in train['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_train_v3/train_delivery_v1/bundle_parts/') and part['bytes']<=4*1024**2,'bounded owned TRAIN part')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==proof['part_git_oids'][name]==git('rev-parse',proof['source_commit']+':'+name).decode().strip(),'TRAIN exact actually restored Git part')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'TRAIN source part bytes')
        train_oids[name]=oid;allowed.add(name)
    records['train_zip_bundle']=dict(index_path=train_index_name,index_sha256=hashlib.sha256(train_raw).hexdigest(),proof_path=train_proof_name,
        proof_sha256=hashlib.sha256(proof_raw).hexdigest(),source_commit=proof['source_commit'],part_git_oids=train_oids,
        original_files=8450,parts=83,exact_gzip_aliases=1296,decoded_canonical_gzip_lines=802542,
        aliases_reuse_complete_canonical_decoded_scan_disclosed=True,no_new_recovery_in_archive=True)
    return allowed,records


'''
    marker='def main():\n';assert s.count(marker)==1;s=s.replace(marker,extra+marker)
    first=s.index("    note=f'''");last=s.index('    extras={',first)
    note='''# 完整TRAIN与固定表现参考训练归档

来源{SOURCE}，父归档{PARENT}。一次完整新NATIVE36与TRAIN648及两级审计通过；
TRAIN602成功/46任务失败，保留全18组、三任务/两条件/三时点、短窗和早结束。
新数据合计85789控制步/34884全部reset/17870945帧；历史失败费用另列。
原始完整8450文件由83个4MiB以内分片恢复；实际Git对象恢复及802542行解码
扫描通过。1296个单例压缩成员由原聚合流精确字节切片恢复，不重编码、不
删除原文件，不把重复存储再计交互或假称重复解码扫描。

一次固定1000预训练+4000META+4000匹配ERM完成，9000 AdamW/66712训练求解，
三个预定checkpoint均保留，无择优。独立数学核对另918求解，通过；它只
检查TRAIN内导出/递归/批后验一致，不是独立预测、校准或完整任务收益。
零在线LLM；全部负结果及旧原始记录保留，未推送原巨型历史或合并。

模型bank与数据分片均来自已检查本地提交。旧7流/28片、Native499文件/10片
的原恢复证明按Git身份复用。科学CAL/QUAL尚未开放，A的新机制/强对照、
独立自身历史任务收益与消融仍待建立，CCF A目标未完成。
源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；全部省略
项在来源目录中明示。原始大文件、ZIP和两次TRAIN恢复仍保留本地。
'''
    s=s[:first]+"    note=f'''"+note+"'''\n"+s[last:]
    s=s.replace('Archive independent qualification obligations and source review without changing ongoing TRAIN','Archive complete audited TRAIN648 records and frozen reference training with independent mathematics')
    s=s.replace("selection='retain prior per-path selection; publish bounded completed controller_agreement, policy_mode_diagnostic and occam_performance_core artifacts after decompressed scan; other raw jsonl.gz, binary .bin, environment and >8MiB remain omitted'",
        "selection='retain prior per-path selections; allow individually proved old, Native and complete TRAIN lossless parts plus bounded checked banks; omit other raw streams, binary parts, environment and >8MiB files'")
    compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
    push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_qualification_review_v1','outputs/research_archive/occam_complete_training_v3')
    (out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);args=p.parse_args();main(args.source)
