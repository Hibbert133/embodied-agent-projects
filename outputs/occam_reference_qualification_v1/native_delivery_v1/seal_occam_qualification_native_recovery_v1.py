"""Seal actual committed-blob recovery separately from the data-containing commit."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/occam_reference_qualification_v1/native_delivery_v1';SOURCE='de7d3541b7af0f24226f141344b3cb4787ba0526'
RUN=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    proof=io.read(OUT/'actual_git_recovery.json');index=io.read(OUT/'bundle_index.json')
    assert proof['integrity']=='PASSED_ACTUAL_COMMIT_QUALIFICATION_NATIVE_PARTS_AND_FILES_RESTORATION' and proof['source_commit']==SOURCE
    assert proof['actual_blob_bytes_not_worktree_shards'] and proof['index_sha256']==io.sha(OUT/'bundle_index.json')
    assert proof['part_count']==len(index['parts'])==12 and proof['result']['files']==len(index['files'])==2288
    assert proof['result']['all_files_byte_identical'] and proof['result']['decoded_canonical_gzip_lines']==158286
    for part in index['parts']:
        n=part['path'];assert git('rev-parse',SOURCE+':'+n).decode().strip()==proof['part_git_oids'][n]
        assert io.sha(ROOT/n)==part['sha256']
    m=io.read(RUN/'manifest.json')
    for n,h in m['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    source_proof=Path(__file__).parent/'occam_core_postcommit_de7d3541b7af.json'
    assert io.read(source_proof)['objects'] and io.read(source_proof)['commit']==SOURCE
    shutil.copyfile(source_proof,OUT/'data_committed_bytes.json');shutil.copyfile(__file__,OUT/Path(__file__).name)
    note=f'''# NATIVE 实际 Git 恢复核对

从数据提交 `{SOURCE}` 的实际 Git blob 读取索引及全部12个分片，
组装ZIP后恢复2288个原始文件，逐文件大小和SHA-256均与原始记录相同。
共有1940个规范文件、348个精确gzip成员别名；158286行规范gzip内容
经基本及补充秘密扫描。别名复用完整规范流的解码扫描，不虚报二次扫描。

这是第二次实际恢复：第一次来源为本地ZIP，第二次来源为已提交Git分片。
两份恢复副本、原始大文件、两个组装ZIP、分片、全部任务失败及封存错误
均保留。复原没有创建、重置或推进环境，没有模型预测、拟合或在线LLM。
13项导出工程检查及四个原归档算法的AST身份核对不算科学资格。

科学冻结提交仍为 `{index['source_git_commit']}`，manifest为
`{index['manifest_id']}`。174次NATIVE是单组运行与数值门；
完整独立QUAL仍按原冻结协议执行，不能由本恢复证明推出任务收益或新颖性。
代码、配置和冻结模型哈希全部核对不变。本次尚未声明数据已远端发布；
是否发布以随后归档的远端回执为准。

核对细节：actual_git_recovery.json；完整分片与原始文件映射：
bundle_index.json；全部174与失败表：all_cases.csv、task_failures.csv。
本证明不替代原始失败或缩减分母。CCF A目标仍未完成。
'''
    with (OUT/'actual_git_recovery_zh.md').open('x',encoding='utf8',newline='\n') as f:f.write(note)
    io.write(OUT/'delivery_complete.json',dict(integrity='PASSED_NATIVE_DELIVERY_WITH_ACTUAL_GIT_RESTORATION',
        data_commit=SOURCE,science_source_commit=index['source_git_commit'],manifest_id=index['manifest_id'],phase='NATIVE',
        files=2288,parts=12,canonical_files=1940,exact_gzip_aliases=348,decoded_canonical_gzip_lines=158286,
        actual_Git_recovery_sha256=io.sha(OUT/'actual_git_recovery.json'),data_committed_bytes_sha256=io.sha(OUT/'data_committed_bytes.json'),
        all_original_raw_zip_restorations_and_failures_preserved=True,current_scientific_source_verified_unchanged=True,
        no_new_physics_or_fits_during_delivery=True,online_LLM_API_calls=0,independent_QUAL_or_novelty_claim=False))
    owned={(OUT/n).relative_to(ROOT).as_posix() for n in ('actual_git_recovery.json','actual_git_recovery_zh.md','data_committed_bytes.json',Path(__file__).name,'delivery_complete.json')}
    def stage(label):
        path=OUT/(label+'.nul');owned.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        git('add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        for n in actual:
            raw=(ROOT/n).read_bytes()
            if n.endswith('.py'):compile(raw,n,'exec')
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('recovery_owned_checked');io.write(OUT/'recovery_index_disk_proof.json',dict(integrity='PASSED',sha256=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'recovery_index_disk_proof.json').relative_to(ROOT).as_posix());stage('recovery_owned_final');check()
    print(dict(integrity='PASSED_ACTUAL_NATIVE_GIT_RECOVERY_STAGED',files=len(owned),source_commit=SOURCE),flush=True)


if __name__=='__main__':main()
