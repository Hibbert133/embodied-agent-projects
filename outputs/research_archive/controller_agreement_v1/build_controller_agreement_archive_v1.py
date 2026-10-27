"""Prepare a bounded ordinary archival checkpoint from the completed delivery."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='c186eb828892c92b6768040c05e9e973c1a7cabb'
assert io.read(ROOT/'outputs/controller_agreement/result_validation_v1/complete.json')['integrity']=='PASSED'
assert not io.git('status','--porcelain','--untracked-files=no')
out=ROOT/'outputs/research_archive/controller_agreement_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/graybox_qualification_v2/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='db378040920c006e37c118576d5f9226c36f86d4'","PARENT='"+parent+"'"),
    ("SOURCE='af2b3c6196bab83670aaf4b1304c2c31cb5cc837'","SOURCE='"+source+"'"),
    ('outputs/research_archive/graybox_result_v1/catalog.json','outputs/research_archive/graybox_qualification_v2/catalog.json'),
    ('research_archive_build_graybox_qualification_20261028_af2b3c6196ba','research_archive_build_controller_agreement_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_GRAYBOX_QUALIFICATION_20261028.json','ARCHIVE_FILE_CATALOG_CONTROLLER_AGREEMENT_20261028.json'),
    ('Archive independent graybox qualification supplement; zero new primary fits or online LLM','Archive TRAIN-only controller agreement feasibility; zero new physics, fits or online LLM')):
    assert old in s,old;s=s.replace(old,new)
old="if (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz'))"
assert old in s;s=s.replace(old,"if (name.startswith('outputs/controller_agreement/') and name.endswith('.gz')) or (name.startswith('outputs/episode_seed_inventory/') and name.endswith('inventory.json.gz'))")
old="allowed=size<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin'))"
assert old in s;s=s.replace(old,"allowed=size<=8*1024**2 and (not name.endswith(('.jsonl.gz','.bin')) or (name.startswith('outputs/controller_agreement/') and name.endswith('.jsonl.gz')))")
old="selection='retain prior per-path selection; new files exclude raw jsonl.gz, binary .bin parts, environment files and >8MiB'"
assert old in s;s=s.replace(old,"selection='retain prior per-path selection; publish bounded controller_agreement jsonl.gz after decompressed scan; other raw jsonl.gz, binary .bin, environment and >8MiB remain omitted'")
i=s.index("    note=f'''");j=s.index('    extras={',i)
note=f'''# 最新归档：A主线共同前缀复用的TRAIN可行性

来源本地 {source}，冻结0272551690b39902cdd275ac6f4f1aa0ae927f4a，父归档 {parent}。
完整648条既有TRAIN、9组、1944个有向速率配对；没有读取CAL/TEST结果筛选。
1608个有采用入口，其中1586个首命令立即分歧；22个至少匹配一步，2个匹配8步
到终局。后两条是同一door-open不变案例的相反方向，不能称两个独立成功。
完整配对分母至少一步1.13%，8步/终局0.10%；有入口组等权平均0.094步，
保守任务损失差范围宽444.878步。完整54联合面板、12速率面板和缺失均保留。

事后描述判断：不足以支持当前共同前缀节省采集路线，封存，不追加该路线样本、
动作容差或选择器。这不是预注册显著性门、无偏OPE、任务收益、新颖性或CCF A。
已知动作一致重放/CIS/DR/事件触发/双重控制/TAMPURA等直接先例不能忽略。
获取机会可能在控制器命令分歧前随状态变化，当前工具没有估计这种机会价值。
用户选择A保持，完整研究目标仍未达到；旧灰箱、历史核、A1等负结果不变。

新增物理/重置/控制步/帧/政策查询/拟合/在线LLM API均为0；实测主规划入口
48315次、独立标量48315次；含哈希重复的PI数值函数静态复算236757次。
历史TRAIN来源77563控制步、33048全部重置、16911815物理帧单列。
20项新增纯数组测试及2428项源码绑定复用共2448项唯一检查；编译、依赖、
全跟踪秘密扫描、实际暂存BASIC/EXTRA与解压扫描、差异及索引字节检查通过。
开发元组/列表错误、交付CRLF错误和原日志/修正前代码均保留，不改科学数据。

报告 reports/controller_agreement_v1_zh.md。本轮小型逐行表发布；历史来源大日志、
旧分片和恢复副本继续本地保留。完整源目录中的发布/省略项及SHA均见
ARCHIVE_FILE_CATALOG_CONTROLLER_AGREEMENT_20261028.json，不宣称全部大数据在远端。
普通快进，无强推、合并、删除历史；存档不计研究贡献。
'''
tail="\n完整本地源树{len(catalog)}项，发布{sum(r['published'] for r in catalog)}项；目录保留完整省略清单。\n"
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:]
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/graybox_qualification_v2/push_graybox_qualification_archive_v2.py').read_text('utf8').replace('outputs/research_archive/graybox_qualification_v2','outputs/research_archive/controller_agreement_v1')
(out/'push_controller_agreement_archive_v1.py').write_bytes(p.encode('utf8'));print(source)
