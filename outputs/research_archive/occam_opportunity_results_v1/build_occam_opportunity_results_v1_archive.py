"""Archive the completed record-only census and its contribution review."""
from pathlib import Path
import subprocess

ROOT = Path('C:/Users/Administrator/Desktop/embodied-agent-projects')
SOURCE = '8d8bdadf610c08ffba5c61e4314f78b8e872b0e5'
PARENT = '46493049dcb4592aff27ed89df4e0cf6794715f2'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == SOURCE
out = ROOT / 'outputs/research_archive/occam_opportunity_results_v1'
out.mkdir(exist_ok=False)
template = ROOT / 'outputs/research_archive/occam_qualification_results_v1'
s = (template / 'archive_checkpoint.py').read_text(encoding='utf-8')
for before, after in [
    ("PARENT='4641010f67defc641b113c950a96aec275a2e83a'", "PARENT='"+PARENT+"'"),
    ("SOURCE='a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'", "SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_costs_review_v1/catalog.json'", "baseline_path=ROOT/'outputs/research_archive/occam_qualification_results_v1/catalog.json'"),
    ('research_archive_build_occam_qualification_results_v1_20261029_a2a4b921bf9a', 'research_archive_build_occam_opportunity_results_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_QUALIFICATION_RESULTS_V1_20261029.json', 'ARCHIVE_FILE_CATALOG_OCCAM_OPPORTUNITY_RESULTS_V1_20261029.json'),
    ('Archive completed negative qualification, first-window diagnostics and full accounting summaries', 'Archive complete post-hoc opportunity census and correction-applicability contribution review')
]:
    assert s.count(before) == 1, before
    s = s.replace(before, after)
i = s.index("    note=f'''")
j = s.index('    extras={', i)
note = '''# A主线：完整固定程序机会普查与查新v10

来源本地{SOURCE}，父归档{PARENT}。先冻结dbae170a956f8cef3ee38376bb9c1f7253de98af，
再一次只读普查，最后本地结果8d8bdadf610c08ffba5c61e4314f78b8e872b0e5。
16项纯构造测试、独立18224项CSV／标量／Fraction检查通过；没有新物理、
政策／模型查询、拟合、训练、episode种子或在线LLM。原1393科学源码及
输入、十项比较统计dccede3a…和已封存接收者保持不变。

全部1740案例、QUAL1566、99任务失败登记，29程序、261组程序行、522格
复算。12项同前缀固定程序菜单54单元、9独立组完整保留：7/54有严格获取
记录差额，47/54无差额，边界前成功8例保留。固定PI_0125继续86.370步，
四个继续程序逐单元事后最低C为86.185，12菜单最低R为64.556；继续增益
记录差额0.185步，获取记录差额21.630步。C／R均使用未来结局，不能作为
可部署损失、期望收益上界、可学习性或算法改进。三例所有固定继续均失败
的单元贡献1116/1168步差额，来自两独立组；只作补充事后描述，不筛人口。
获取差额包含物理路径／等待／记忆／反馈，不能称新增信息纯价值。

查新v10核对D-World、控制诱发分布变化的conformal迭代、动作条件风险、
ASID／SPI-Active及Behavioral Exploration的明示阅读范围。已有双重控制、
模型修订成本和条件校准不改名成贡献；未验证来源和未读证明明确披露。
十二候选及否决理由保留，尚无合格新机制或CCF A完成证据。

下一交付为独立冻结的TRAIN完整后继标签／公开历史支持审计，不是立即
训练或采集。TRAIN648为三获取×两行为×18组，不是四T×三获取全终局表；
RANDOM_WINDOW的未来终局不能贴给一直保持首T的控制器，也不能由QUAL
补齐TRAIN。标准完整风险／DR、被动适应、重加权与全部强参考继续保留。

当前源树{len(catalog)}个已提交文件，发布{sum(r["published"] for r in catalog)}项；
对源树省略项保留完整大小／SHA。原始QUAL事件／witness仍本地保留、不在
此次source Git树；完整ZIP／分片／三种恢复尚待磁盘空间。元数据清单不
冒充内容恢复证明。旧133分片仅按实际Git身份复用历史完整恢复证明，
本次没有新恢复、重采、回滚、合并或强推。当前原始资格仍是执行／预测
通过、完整任务收益未通过。完整A机制、独立自身历史优势及消融仍缺失。
'''
s = s[:i] + "    note=f'''" + note + "'''\n" + s[j:]
compile(s, 'archive_checkpoint.py', 'exec')
(out / 'archive_checkpoint.py').write_text(s, encoding='utf-8', newline='\n')
push = (template / 'push_archive.py').read_text(encoding='utf-8')
assert push.count('outputs/research_archive/occam_qualification_results_v1') == 1
push = push.replace('outputs/research_archive/occam_qualification_results_v1', 'outputs/research_archive/occam_opportunity_results_v1')
compile(push, 'push_archive.py', 'exec')
(out / 'push_archive.py').write_text(push, encoding='utf-8', newline='\n')
pre = (Path(__file__).parent / 'verify_occam_qualification_results_prepublication_v1.py').read_text(encoding='utf-8')
for before, after in [('occam_qualification_results_v1', 'occam_opportunity_results_v1'),
    ("SOURCE = 'a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'", "SOURCE = '"+SOURCE+"'"),
    ("BASE_SOURCE = '017ba38e7c147cc88ac197218ef1bf69f391b3c6'", "BASE_SOURCE = 'a2a4b921bf9a3127ffcf71505cfda24c98f63a0f'")]:
    assert pre.count(before) == 1, before
    pre = pre.replace(before, after)
compile(pre, 'verify_occam_opportunity_results_prepublication_v1.py', 'exec')
(Path(__file__).parent / 'verify_occam_opportunity_results_prepublication_v1.py').write_text(pre, encoding='utf-8', newline='\n')
print(dict(prepared_for_source=SOURCE, archive_parent=PARENT))
