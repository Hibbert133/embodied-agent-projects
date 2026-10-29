"""Append a verified remote summary archive to the local research log."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path('C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0, str(ROOT))
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA

OUT = ROOT / 'outputs/research_archive/occam_opportunity_results_v1'
AUX = Path(__file__).parent
SOURCE = '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'
ARCHIVE = '03fa9655ad4a6bdee6ca2b15adf213167cd4984b'
RUN = ROOT / 'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085'


def git(*args):
    return subprocess.check_output(['git', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', *args], cwd=ROOT)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    remote = read(OUT / 'remote_receipt.json')
    local = read(OUT / 'local_receipt.json')
    pre = read(OUT / 'prepublication_proof.json')
    assert remote['integrity'] == local['integrity'] == 'PASSED'
    assert remote['remote_after'] == local['archive_commit'] == pre['archive_commit'] == ARCHIVE
    assert pre['phase_files'] == 75 and pre['phase_bytes'] == 6334561 and pre['phase_omitted'] == 0
    assert git('rev-parse', 'HEAD').decode().strip() == SOURCE
    assert not git('status', '--porcelain', '--untracked-files=no').strip()
    assert git('ls-remote', '--heads', 'origin', 'refs/heads/' + remote['branch']).decode().split()[0] == ARCHIVE
    counters = []
    for commit, label in [
        ('bb120f1c554e27937c4ce1bad76d77423a07ce5e', 'previous_archive_metadata_committed_bytes'),
        ('dbae170a956f8cef3ee38376bb9c1f7253de98af', 'opportunity_freeze_committed_bytes'),
        (SOURCE, 'opportunity_result_committed_bytes')
    ]:
        path = AUX / ('occam_core_postcommit_' + commit[:12] + '.json')
        proof = read(path)
        assert proof['integrity'] == 'PASSED' and proof['commit'] == commit
        counters.append((proof['object_count'], proof['bytes']))
        shutil.copyfile(path, OUT / (label + '.json'))
    assert sum(n for n, _ in counters) == 75 and sum(n for _, n in counters) == 6334561
    manifest = read(RUN / 'manifest.json')
    for name, digest in {**manifest['source_sha256'], **manifest['input_sha256']}.items():
        assert sha(ROOT / name) == digest
    assert sha(RUN / 'statistics_v1/statistics.json') == 'dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc'
    for name in ['build_occam_opportunity_results_v1_archive.py',
                 'verify_occam_qualification_results_prepublication_v1.py', 'log_occam_opportunity_results_v1.py']:
        shutil.copyfile(AUX / name, OUT / name)
    assert sha(ROOT / 'outputs/occam_opportunity_census_v1/analysis_v1/statistics.json') == '0214bd46cb101b982de982ca93e75b228cf218d09bad97abf28b490b660c960a'
    log = ROOT / 'Research_Log.md'
    old = log.read_bytes()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition = f'''

## {stamp}（北京时间）｜A主线完整固定程序机会普查与查新v10归档

- 先本地冻结dbae170a956f8cef3ee38376bb9c1f7253de98af：25文件257561字节，
  16项纯构造测试开发／正式各16执行，不算32个不同测试。旧2695科学
  检查与编译按1393源码及输入复用，未重跑仿真；冻结前禁止语义解析
  实际CSV。源码／输入、依赖、239.3527003秒秘密、补扫、差异与索引通过。
- 一次实际只读普查工作进程0.7313194秒、父过程1.4558944秒；独立
  CSV／标量／Fraction核对18224项，主模块全部10个函数禁用。共享
  CSV／JSON／SHA工具，不称物理重仿真。全部1740分配、QUAL1566与99
  失败登记，29程序、261组程序行、522格完整复算。实际CSV6读、7163行、
  668450字节，JSON、哈希、父准入和绘图费用另记。
- 同前缀12个固定程序的54单元、9独立组中，获取严格记录差额7/54，
  无差额47/54；提前成功8例不删除。固定PI_0125继续86.370步，四个
  CONTINUE逐单元事后最低C86.185，12菜单事后最低R64.556；增益选择
  记录差额0.185、获取记录差额21.630。它们使用未来结局及每程序一次
  噪声实现，不能作可部署损失、可学习性、期望收益上界或纯信息收益。
- 全部精确获取差额频数：0步47、1步2、3／47／359／360／397步各1。
  补充事后描述中，三个所有固定CONTINUE均失败单元贡献1116/1168步，
  来自两个独立组；不认定唯一原因，不据此缩人口。固定T在移动分支
  也可恢复，状态／等待／记忆／反馈影响未与新增信息分离。
- 结果提交`{SOURCE}`：31文件1450131字节与实际Git／磁盘一致；完整
  原图54单元、全部频数、18格及原失败保留。197.4013789秒秘密扫描、
  索引基本／EXTRA、依赖、编译与两差异通过，16项源绑定检查不重复。
  原十项统计dccede3a…、执行／预测通过而任务资格失败及封存决定不变；
  新统计0214bd46…已绑定。新增环境／reset／帧／政策或模型查询／拟合／
  训练／episode种子／在线LLM均0；guard有意拒绝测试不称实际网络／环境。
- v10原文检索与两技能问题优先／失败边界／简单参考筛选登记12候选。
  D-World、内生漂移conformal、动作条件风险、ASID／SPI-Active与上下文
  行为探索的已读范围、条件与未核实403线索均披露。测量修订、闭环
  展开、门控、信息矩阵、普通重加权和多头风险不自动成为新贡献。
- 下一件是独立冻结的TRAIN公开历史／完整后继标签支持审计，不立即
  训练或采集。TRAIN648来自三获取×两行为×18组，不是四T完整反事实
  表；随机后续的终局不贴给保持首T的程序，QUAL不回填TRAIN。实际
  时序支持、角色及原行为概率须先核对，标准完整风险／DR仍是强参考。
- 75个阶段文件6334561字节在推送前逐项比对实际归档对象／磁盘；
  本次10704归档文件、65个新源对象秘密扫描、6334441新Git字节哈希。
  普通快进并再次核对远端`{ARCHIVE}`，无合并／强推；旧133分片按精确
  Git身份复用历史恢复证明，没有新恢复。完整原始QUAL仍本地保留、
  ZIP／分片／三种恢复待空间，元数据清单不冒充内容恢复。本条远端
  核对后追加，本地元数据提交不递归推送。
- [中文机会普查](reports/occam_opportunity_census_v1_zh.md)。当前没有
  合格新算法、独立自身历史任务优势或消融；A方向和CCF A目标完整保留、
  继续未完成，不以标准菜单差额、测试或存档代替贡献。
'''
    with log.open('ab') as stream:
        stream.write(addition.encode('utf-8'))
    assert log.read_bytes()[:len(old)] == old
    write(OUT / 'complete.json', dict(integrity='PASSED_OPPORTUNITY_CENSUS_ARCHIVE_APPEND_ONLY_LOG',
        source_local_commit=SOURCE, remote_archive_commit=ARCHIVE, phase_published=75, phase_omitted=0,
        phase_bytes=6334561, previous_log_bytes=len(old), previous_log_sha256=hashlib.sha256(old).hexdigest(),
        new_log_sha256=sha(log), append_only=True, scientific_population_complete=True,
        numerical_qualification=True, predictive_qualification=True, task_qualification=False,
        full_raw_QUAL_archive_complete=False, original_raw_records_and_restorations_preserved=True,
        scientific_source_files_unchanged=1393, new_environment_interactions=0,
        new_real_model_queries=0, new_fits=0, online_LLM_API_calls=0, publication_goal_complete=False))
    owned = {'Research_Log.md'} | {p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}

    def stage(label):
        spec = OUT / (label + '.nul')
        owned.add(spec.relative_to(ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode('utf-8') for n in sorted(owned)) + b'\0')
        for flags in ((), ('--renormalize',)):
            git('add', *flags, '--pathspec-from-file=' + spec.relative_to(ROOT).as_posix(), '--pathspec-file-nul')

    def check():
        objects = index_bytes(owned)
        assert set(objects) == owned
        for name in objects:
            data = (ROOT / name).read_bytes()
            if name.endswith('.py'):
                compile(data, name, 'exec')
            if b'\0' not in data:
                text = data.decode('utf-8')
                assert find_secret_rule(text) is None and not any(rule.search(text) for rule in EXTRA.values())
        assert not git('diff', '--check').strip() and not git('diff', '--cached', '--check').strip()
        return objects

    stage('owned_checked')
    write(OUT / 'index_disk_proof.json', dict(integrity='PASSED', objects=check(), actual_index_basic_EXTRA_scan=True))
    owned.add((OUT / 'index_disk_proof.json').relative_to(ROOT).as_posix())
    stage('owned_final')
    objects = check()
    print(dict(integrity='PASSED_APPEND_ONLY_RESULT_ARCHIVE_LOG', files=len(objects), remote_archive_commit=ARCHIVE))


if __name__ == '__main__':
    main()
