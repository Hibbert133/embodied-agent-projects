from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source='c49b4268eb4e739256fcd7e2d9b3a2fed976198f';parent='e642553f55bf906e13b7fccf2e5163bc627f307a'
assert io.git('rev-parse','HEAD')==source
out=ROOT/'outputs/research_archive/occam_native_qualification_v3';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_isolated_training_log_v3';s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (("PARENT='587128a167e0a4ea909072134693aa33efd5468f'","PARENT='"+parent+"'"),
    ("SOURCE='c92356173d9e99dada69da6a032f880a4f763259'","SOURCE='"+source+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_isolated_training_freeze_v3/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_isolated_training_log_v3/catalog.json'"),
    ('research_archive_build_occam_isolated_log_v3_20261028_c92356173d9e','research_archive_build_occam_native_v3_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_ISOLATED_LOG_V3_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_NATIVE_V3_20261028.json')):
    assert before in s,before;s=s.replace(before,after)
old="""    return allowed,dict(strategy='reuse seven actual Git stream recoveries only after exact Git object identity for every index, part and collection completion',
        prior_archive_commit=PARENT,prior_catalog_sha256=hashlib.sha256(baseline_bytes).hexdigest(),unchanged_git_objects=bindings,
        indices=prior['decoded_record_parts']['indices'],new_recovery_or_physics=False)
"""
new="""    native_index_name='outputs/occam_reference_train_v3/native_delivery_v1/bundle_index.json'
    native_proof_name='outputs/occam_reference_train_v3/native_delivery_v1/actual_git_recovery.json'
    native_raw=git('show',SOURCE+':'+native_index_name);native_index=json.loads(native_raw)
    native_proof_raw=git('show',SOURCE+':'+native_proof_name);native_proof=json.loads(native_proof_raw)
    io.require(native_raw==(ROOT/native_index_name).read_bytes() and native_proof_raw==(ROOT/native_proof_name).read_bytes(),'native immutable proof bytes')
    io.require(native_index['schema']=='OCCAM_NATIVE_ZIP_PARTS_V1' and native_proof['integrity']=='PASSED_ACTUAL_COMMIT_PARTS_AND_FILES_RESTORATION'
        and native_proof['index_sha256']==hashlib.sha256(native_raw).hexdigest() and native_proof['source_commit']=='d2dc35e56e174a1e26388068f617f82caf89df34'
        and native_proof['result']['files']==len(native_index['files'])==499 and native_proof['part_count']==len(native_index['parts'])==10,'complete native actual Git restoration')
    native_oids={}
    for part in native_index['parts']:
        name=part['path'];io.require(name.startswith('outputs/occam_reference_train_v3/native_delivery_v1/bundle_parts/') and name.endswith('.bin') and part['bytes']<=4*1024**2,'bounded native parts only')
        oid=git('rev-parse',SOURCE+':'+name).decode().strip()
        io.require(oid==native_proof['part_git_oids'][name]==git('rev-parse',native_proof['source_commit']+':'+name).decode().strip(),'same actually restored native object')
        data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256'],'native source part bytes')
        native_oids[name]=oid;allowed.add(name)
    return allowed,dict(strategy='reuse historical actual recoveries after exact Git identity; native499-file ZIP has its own committed actual recovery and decoded credential scan',
        prior_archive_commit=PARENT,prior_catalog_sha256=hashlib.sha256(baseline_bytes).hexdigest(),unchanged_git_objects=bindings,
        indices=prior['decoded_record_parts']['indices'],new_recovery_or_physics=False,
        native_zip_bundle=dict(index_path=native_index_name,index_sha256=hashlib.sha256(native_raw).hexdigest(),proof_path=native_proof_name,
            proof_sha256=hashlib.sha256(native_proof_raw).hexdigest(),source_commit=native_proof['source_commit'],part_git_oids=native_oids,
            files=499,parts=10,decoded_gzip_lines=native_proof['result']['decoded_gzip_lines']))
"""
assert old in s;s=s.replace(old,new)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 标准表现参考v3原生资格与完整记录

来源{SOURCE}，父归档{PARENT}。新资源达门后一次Native36完整，进程/字节/
会计及完整动态/PI/动作/噪声/连续见证双审计通过，18对共同获取后完整
状态一致，295个实际窗口。35任务成功/1失败/0技术失败，全部保留；只有
一个独立组和边界16，不作为算法胜出、独立模型/任务或CCF A证据。

实际5399控制步/1836全部reset/944995物理帧；实际及独立重放政策查询
各5083，在线LLM、科学拟合、Adam均0。原始数据与所有回执/日志499文件
完整ZIP分10个4MiB以内分片；从实际提交Git对象恢复并逐文件核对，91106
gzip行秘密扫描通过。原ZIP/原数据/两次恢复副本保留，不含变化中的TRAIN。

旧7流/28片实际恢复证明仅在全部相关Git对象一致后复用，新增Native10片
另附已提交恢复证明；不能把38片或499文件当独立科学样本。完整TRAIN648
按冻结分配运行，全部双审计前不能学习；未来模型、资格及自身历史任务
评价另行核对，强完整风险/DR等对照与A主线具体贡献仍待建立。

源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项，全部省略
条目在目录中列明。普通快进，无强推合并，原始历史/负结果保持。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive isolated collector stage log, complete publication proof and rejected preflight','Archive native qualification with full raw record bundle, all failures and actual Git recovery')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_isolated_training_log_v3','outputs/research_archive/occam_native_qualification_v3')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n');print(source,flush=True)
