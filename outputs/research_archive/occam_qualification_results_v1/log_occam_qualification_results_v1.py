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

OUT = ROOT / 'outputs/research_archive/occam_qualification_results_v1'
AUX = Path(__file__).parent
SOURCE = 'a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'
ARCHIVE = '46493049dcb4592aff27ed89df4e0cf6794715f2'
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
    assert pre['phase_files'] == 226 and pre['phase_bytes'] == 27400913 and pre['phase_omitted'] == 0
    assert git('rev-parse', 'HEAD').decode().strip() == SOURCE
    assert not git('status', '--porcelain', '--untracked-files=no').strip()
    assert git('ls-remote', '--heads', 'origin', 'refs/heads/' + remote['branch']).decode().split()[0] == ARCHIVE
    counters = []
    for commit, label in [
        ('33eb50dd25610763e3f24eaf59dd9d3f94384d52', 'previous_archive_metadata_committed_bytes'),
        ('d6f1bad4bff34a31d210ae2ec94045bd517b6af9', 'accounting_v2_freeze_committed_bytes'),
        (SOURCE, 'qualification_summary_committed_bytes')
    ]:
        path = AUX / ('occam_core_postcommit_' + commit[:12] + '.json')
        proof = read(path)
        assert proof['integrity'] == 'PASSED' and proof['commit'] == commit
        counters.append((proof['object_count'], proof['bytes']))
        shutil.copyfile(path, OUT / (label + '.json'))
    assert sum(n for n, _ in counters) == 226 and sum(n for _, n in counters) == 27400913
    manifest = read(RUN / 'manifest.json')
    for name, digest in {**manifest['source_sha256'], **manifest['input_sha256']}.items():
        assert sha(ROOT / name) == digest
    assert sha(RUN / 'statistics_v1/statistics.json') == 'dccede3a2838fb1ef98c20bab5e89080bcd42c8a53629c1ad22d646ae6fb75bc'
    for name in ['build_occam_qualification_results_v1_archive.py',
                 'verify_occam_qualification_results_prepublication_v1.py', 'log_occam_qualification_results_v1.py']:
        shutil.copyfile(AUX / name, OUT / name)
    log = ROOT / 'Research_Log.md'
    old = log.read_bytes()
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    addition = f'''

## {stamp}（北京时间）｜完整资格负结果、首窗口诊断与成本摘要归档

- 一次性科学冻结7abaec83b085完整完成NATIVE174及QUAL1566，共1740执行，
  99任务失败保留、未解决0。九步收集／双审计／统计／独立统计／报告
  全部返回0。数值／执行与预测资格通过，完整任务收益资格未通过。
- 主方法META_ADAPT__CONTINUE为51/54、86.500步；同前缀边界后固定
  PI_0125为51/54、86.370。十项主比较七项满足、三项未满足；对同前缀
  PI_0125、GLOBAL_PI_2000和ERM_ADAPT的区间跨零。失败门不等于证明
  劣势，优于旧C8／积分对照也不替代全部强参考。当前接收者封存，不
  调bank、beta、窗口、获取门或样本数，不改主比较，不用旧QUAL选后继。
- 原预测仅46/54有事实窗口，其余8保留。首窗口事后诊断登记1566，
  1296胶囊、162起点、216格；136可用、26无首窗。META MSE约0.000640，
  组等权排序错误约0.361；固定首窗对固定完整结局排序错误约0.337。
  不能把固定终局贴给自适应后续，或把错误唯一归因模型／时域。独立
  记录与Fraction审计通过，耗时110.5584878秒，新增物理／模型／API0。
- 显式accounting成本v2核对全部1740例，独立复算通过，18.076368秒；
  v1对120旧格式缺失case字段的失败保留，未把缺失默认0。v2冻结15新
  测试通过；旧25成本及2695科学检查按源码复用。实际187405控制步、
  88740全部reset、45307025物理帧；共同NN训练9000更新和全部历史来源
  单列，不按程序重复计费。在线LLM／tokens0，平均API延迟null。
- 结果交付提交`{SOURCE}`，183文件21986786字节实际Git／磁盘一致。
  报告、29程序、522格、全部失败、首窗胶囊、成本、来源／封存回执及
  PNG／SVG保留。五项交付大小／范围／换行检查停止及纠正解释均保留；
  原种子元数据精确gzip可逆，CSV／SVG原字节未改。全量秘密扫描
  223.2368591秒、补充实际索引gzip／EXTRA、编译、依赖和两类差异通过。
- 归档前226个阶段源文件27400913字节与实际归档对象／磁盘核对一致，
  当前归档10629文件；184个新发布对象秘密扫描，26423536新Git字节
  哈希。普通快进后再次核对远端`{ARCHIVE}`，未合并／强推。旧133分片
  按精确Git身份复用历史完整恢复证明，无新恢复或采集。原1393源码及
  输入、原统计dccede3a…再次核对不变。
- 本次只是完整结果的统计／诊断摘要归档。完整QUAL原始事件／witness
  仍本地保留，不在此次source Git树；完整ZIP／分片及三种恢复尚待
  空间。元数据路径／字节清单不是原始内容哈希或恢复证明，不降门、不
  删除原记录／副本。本条在远端复核后追加，元数据只本地提交，不递归推送。
- [中文结果解释](reports/occam_reference_qualification_v1_delivery_zh.md)。
  A方向新机制、相对DR／重加权／被动适应／MDE／OCCAM／GAUGE／Poke／
  条件监测的具体区别、独立完整任务优势及消融仍待建立，CCF A目标未完成。
'''
    with log.open('ab') as stream:
        stream.write(addition.encode('utf-8'))
    assert log.read_bytes()[:len(old)] == old
    write(OUT / 'complete.json', dict(integrity='PASSED_RESULT_SUMMARY_ARCHIVE_APPEND_ONLY_LOG',
        source_local_commit=SOURCE, remote_archive_commit=ARCHIVE, phase_published=226, phase_omitted=0,
        phase_bytes=27400913, previous_log_bytes=len(old), previous_log_sha256=hashlib.sha256(old).hexdigest(),
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
