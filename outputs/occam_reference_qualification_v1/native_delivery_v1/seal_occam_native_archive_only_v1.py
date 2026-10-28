"""Seal a real restoration that is denied access to the original record tree."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
BASE=ROOT/'outputs/occam_reference_qualification_v1';OUT=BASE/'native_delivery_v1';TOOLS=BASE/'delivery_tools_v1'
SOURCE='8f197877f3874bd6033b58f31b283163813fcbaa'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    proof=io.read(OUT/'archive_only_restoration.json');prior=io.read(OUT/'actual_git_recovery.json');index=io.read(OUT/'bundle_index.json')
    assert proof['integrity']=='PASSED_ACTUAL_GIT_ARCHIVE_ONLY_NATIVE_RESTORATION' and proof['containing_commit']==SOURCE
    assert proof['part_git_oids']==prior['part_git_oids'] and proof['index_sha256']==io.sha(OUT/'bundle_index.json')
    assert proof['result']['files']==2288 and proof['result']['decoded_canonical_gzip_lines']==158286
    assert not proof['result']['original_raw_files_required'] and not proof['result']['original_raw_byte_comparison']
    assert proof['result']['size_and_SHA_against_committed_index'] and not any(proof['guard'].values())
    validation=io.read(TOOLS/'archive_only_validation_v1/complete.json');assert validation['unit_tests']==3
    for n,h in validation['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    note='''# 从归档独立恢复 NATIVE 数据

已用实际Git分片恢复全部2288个文件，并在运行时禁止读取原来的NATIVE／
QUAL记录树，读取尝试为0；无需本机原始大文件。每个规范文件与gzip成员
别名均按提交索引中的长度／SHA-256检查，158286行规范gzip又做解码秘密
扫描。此模式不与原件比较字节；另两次本地ZIP和实际Git恢复已与原件比较。

本入口复用已检查的归档算法，不改变原严格原件核对入口。3个新增工程
检查覆盖原件不存在／禁止读取、坏索引文件哈希、被改ZIP；不算科学资格。
没有新环境、策略／模型调用、拟合或在线LLM。没有实际执行完整新clone的
依赖安装测试；入口需要本仓库代码和相应既有Python依赖。

在包含这些分片的仓库提交中，从仓库根目录执行以下PowerShell示例。
目标恢复目录与收据必须尚不存在。远端使用实际归档HEAD；原科学冻结提交
或原本地数据提交编号未必存在于精简归档历史，不能拿它们代替。

```powershell
$nativeArchiveCommit = (git rev-parse HEAD).Trim()
python outputs/occam_reference_qualification_v1/delivery_tools_v1/recover_native_archive_only_v1.py --source $nativeArchiveCommit --restore C:/Research/native-restore --receipt C:/Research/native-restore-receipt.json
```

C:/Research父目录需存在，也可换成有空间的可写位置。不会覆盖已有恢复
目录；组装ZIP和恢复数据均保留。收据记录实际使用的Git对象身份、索引
哈希、原件读取护栏和完整文件数。SHA校验是记录完整性检查，不是物理／
预测／任务收益／安全保证。NATIVE只有单组，独立QUAL仍按原冻结设计执行。
'''
    with (OUT/'archive_only_recovery_zh.md').open('x',encoding='utf8',newline='\n') as f:f.write(note)
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    io.write(OUT/'archive_only_complete.json',dict(integrity='PASSED_NATIVE_ARCHIVE_ONLY_RESTORATION_DELIVERY',
        source_parent_commit=SOURCE,raw_tree_read_attempts=0,files=2288,part_count=12,
        proof_sha256=io.sha(OUT/'archive_only_restoration.json'),validation_sha256=io.sha(TOOLS/'archive_only_validation_v1/complete.json'),
        original_raw_files_required=False,original_comparison_not_claimed_for_this_mode=True,
        existing_original_comparison_proofs_preserved=True,new_engineering_tests=3,new_scientific_tests=0,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,full_fresh_clone_test_not_performed=True))
    owned={(TOOLS/n).relative_to(ROOT).as_posix() for n in ('recover_native_archive_only_v1.py','test_archive_only_restore_v1.py','validate_archive_only_v1.py')}
    owned|={p.relative_to(ROOT).as_posix() for p in (TOOLS/'archive_only_validation_v1').iterdir() if p.is_file()}
    owned|={(OUT/n).relative_to(ROOT).as_posix() for n in ('archive_only_restoration.json','archive_only_recovery_zh.md','archive_only_complete.json',Path(__file__).name)}
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
    stage('archive_only_owned_checked');io.write(OUT/'archive_only_index_disk_proof.json',dict(integrity='PASSED',sha256=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'archive_only_index_disk_proof.json').relative_to(ROOT).as_posix());stage('archive_only_owned_final');check()
    print(dict(integrity='PASSED_ARCHIVE_ONLY_RESTORATION_STAGED',files=len(owned),new_engineering_tests=3),flush=True)


if __name__=='__main__':main()
