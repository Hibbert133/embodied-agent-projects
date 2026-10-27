"""Bounded archival snapshot of the completed descriptive diagnostic."""
from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='9f655181461627bf256e1ff72973814534676227'
assert io.read(ROOT/'outputs/policy_mode_diagnostic/result_validation_v1/complete.json')['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no')
out=ROOT/'outputs/research_archive/policy_mode_diagnostic_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/controller_agreement_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='c186eb828892c92b6768040c05e9e973c1a7cabb'","PARENT='"+parent+"'"),
    ("SOURCE='28781c8076f4fdd17eb05cba042d4292a902c3b4'","SOURCE='"+source+"'"),
    ('outputs/research_archive/graybox_qualification_v2/catalog.json','outputs/research_archive/controller_agreement_v1/catalog.json'),
    ('research_archive_build_controller_agreement_20261028_28781c8076f4','research_archive_build_policy_mode_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_CONTROLLER_AGREEMENT_20261028.json','ARCHIVE_FILE_CATALOG_POLICY_MODE_20261028.json'),
    ("name.startswith('outputs/controller_agreement/')","name.startswith(('outputs/controller_agreement/','outputs/policy_mode_diagnostic/'))"),
    ('Archive TRAIN-only controller agreement feasibility; zero new physics, fits or online LLM','Archive TRAIN-only policy-mode functional diagnostic; zero new physics, fits or online LLM')):
    assert old in s,old;s=s.replace(old,new)
s=s.replace('publish bounded controller_agreement jsonl.gz after decompressed scan','publish bounded controller_agreement and policy_mode_diagnostic jsonl.gz after decompressed scan')
i=s.index("    note=f'''");j=s.index('    extras={',i)
note=f'''# 最新归档：固定政策模式与连续反馈的TRAIN函数诊断

本地来源 {source}，冻结074ef5632712f50ce1d1a811c0cd2a689feacbf2，父归档 {parent}。
648条既有TRAIN、972无向实际配对、5832窗口、2214全分层及21656实际配对步。
全部事后描述；不读取CAL/TEST/旧QUAL内容来选择，不是新独立机器人试验。

预指定H2的803/972完整窗中，61.6255%有Z/夹爪发送差，但两程序政策叶始终相同，
模式项精确为0，发送差L1仅4.0724134e-6，来自连续反馈。H4模式项也为0。
这反驳“第二步字节差意味着模式跳变”，不解锁该模式门控或追加数据。
H8/16/32出现模式函数项，但可用人口改变，分量可抵消，也可能是有益任务推进，
不能把所有模式变化当不利更新、唯一植物失配原因或提前获取收益。

新增环境/重置/控制步/帧/机器人政策查询/拟合/在线LLM API均0；主/独立各
133191次固定叶函数展开；合成开发18+正式18次政策函数查询另列。
历史TRAIN来源648执行、77563步、33048全部重置、16911815物理帧单列。
15项新增纯数组检查、2448项源码绑定复用，共2463唯一检查；编译、依赖、
秘密、实际暂存BASIC/EXTRA解压扫描、差异和索引字节均通过。原夹具/配置写入
失败、字体缺字图及源稿保留；CSV/日志原字节压缩保留，不改科学数值。

大窗口JSON原件和实际恢复副本本地保留，两个4MiB级分片及索引本地提交；
同字节gzip替代已验证，可在紧凑归档恢复完整窗口。普通二进制分片不发布，
全部省略/发布、大小与SHA见ARCHIVE_FILE_CATALOG_POLICY_MODE_20261028.json。
全部报告与证据见reports/policy_mode_diagnostic_v1_zh.md。

当前只是标准政策函数分解，不是新颖性、因果植物诊断、完整任务收益、安全或
CCF A。A主线、原六项比较和全部旧负结果保持；无强推、合并或删除历史。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项，完整目录保留省略清单。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/controller_agreement_v1/push_controller_agreement_archive_v1.py').read_text('utf8').replace('outputs/research_archive/controller_agreement_v1','outputs/research_archive/policy_mode_diagnostic_v1')
(out/'push_policy_mode_archive_v1.py').write_bytes(p.encode('utf8'));print(source)
