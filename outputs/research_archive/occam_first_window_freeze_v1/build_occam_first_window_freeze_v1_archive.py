"""Publish a completed record-only diagnostic freeze, excluding live QUAL files."""
from pathlib import Path
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
SOURCE=sys.argv[1];PARENT='819afbe3252e8d7fd6a45b9d22699cfd6bed6170'
assert len(SOURCE)==40 and all(x in '0123456789abcdef' for x in SOURCE)
assert subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0','rev-parse','HEAD'],cwd=ROOT).decode().strip()==SOURCE
out=ROOT/'outputs/research_archive/occam_first_window_freeze_v1';out.mkdir(exist_ok=False)
template=ROOT/'outputs/research_archive/occam_receiver_prefix_v1'
s=(template/'archive_checkpoint.py').read_text(encoding='utf8')
for before,after in (
    ("PARENT='e3b43c1ddaca52a4a9def9cea14f90856fea9ba2'","PARENT='"+PARENT+"'"),
    ("SOURCE='4fb646a93bac29fcf2b6422c60a562dad7bddf0d'","SOURCE='"+SOURCE+"'"),
    ("baseline_path=ROOT/'outputs/research_archive/occam_qualification_native_v1/catalog.json'","baseline_path=ROOT/'outputs/research_archive/occam_receiver_prefix_v1/catalog.json'"),
    ('research_archive_build_occam_receiver_prefix_v1_20261029_4fb646a93bac','research_archive_build_occam_first_window_freeze_v1_20261029_'+SOURCE[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_RECEIVER_PREFIX_V1_20261029.json','ARCHIVE_FILE_CATALOG_OCCAM_FIRST_WINDOW_FREEZE_V1_20261029.json')):
    assert before in s,before;s=s.replace(before,after)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note='''# 首窗口四候选只读诊断：软件冻结归档

来源{SOURCE}，父归档{PARENT}。已完成诊断reader、严格终态准入、162起点／
1296同前缀记录／216完整分层的设计实现、独立literal／Fraction复算器。
尚无本诊断全人口结果，不改变正在运行的独立资格实验或原十项主比较。
准入要求完整QUAL1566、进程／动态审计、原统计及独立复算完整性和原
一次性pipeline结束；科学收益门为负仍可事后诊断，部分／技术关闭不能进入。
真实运行路径已在任何QUAL结局读取前按预期拒绝，没有创建analysis目录。

43个不同构造／数组测试通过；开发40+43、正式43，共126测试执行。
对齐核对原生／Python见证、全部过去历史、物理前缀、记忆、噪声游标、
时钟与保存查询／声明；短窗、失败、缺失及强对照完整保留。首窗预测／
排序和恒定程序完整损失对应仅事后描述，不改名完整Q或可部署收益。
同bank适应／冻结首窗不是独立样本。审计禁用主诊断函数，JSON codec、
准入及哈希共享已披露，不是独立物理重仿真或机器人安全保证。

现行科学1393来源与输入哈希不变，旧资格2695检查按冻结来源／回执复用；
新工具编译、依赖、秘密／补充秘密、普通／暂存差异、索引／磁盘／实际
Git字节均核对。新增环境、重置、帧、政策查询、模型前向、后验、拟合、
训练、seed及在线LLM0，当前QUAL独立费用不归零。全部旧负结果、原始记录、
分片和实际恢复副本保留；133原有记录分片按精确Git身份和原恢复证明复用，
此次归档不重新采集或恢复。当前仍运行的QUAL原始文件不在本归档中。

若当前接收者不具竞争力，保持封存，不在它上面再叠获取门。本冻结只是
诊断准备；A的新机制、同权限完整风险／DR／普通重加权强参考、独立自身
历史任务收益、新颖性与消融仍未完成，不能据此称CCF A工作完成。
当前源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；
省略源有完整大小／SHA目录，不把省略原始文件称为已远端交付。
'''
s=s[:i]+"    note=f'''"+note+"'''\n"+s[j:]
s=s.replace('Archive complete TRAIN receiver-prefix support with independent arithmetic, missing task outcomes and full costs',
            'Archive record-only four-candidate diagnostic software freeze before complete qualification results')
compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_text(s,encoding='utf8',newline='\n')
push=(template/'push_archive.py').read_text(encoding='utf8').replace('outputs/research_archive/occam_receiver_prefix_v1','outputs/research_archive/occam_first_window_freeze_v1')
(out/'push_archive.py').write_text(push,encoding='utf8',newline='\n')
print(dict(prepared_for_source=SOURCE,archive_parent=PARENT),flush=True)
