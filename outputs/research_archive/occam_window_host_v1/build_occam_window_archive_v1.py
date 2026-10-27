from pathlib import Path
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
source=io.git('rev-parse','HEAD');parent='ff5610d3e44b44c92351d9fb7d2c0b280c4f9c56'
assert source=='ff05ef4e5f10e5da683f14f8a6ffd9603c7825b9' and io.read(ROOT/'outputs/occam_window_host/delivery_v1/complete.json')['integrity']=='PASSED'
out=ROOT/'outputs/research_archive/occam_window_host_v1';out.mkdir(exist_ok=False)
s=(ROOT/'outputs/research_archive/occam_performance_core_v1/archive_checkpoint.py').read_text('utf8')
for old,new in (("PARENT='7ff790502118e695a6ded410c9c3a8c21731977c'","PARENT='"+parent+"'"),
    ("SOURCE='a37a003caef7ef07b9f26adbda49f464a76e140d'","SOURCE='"+source+"'"),
    ('outputs/research_archive/policy_mode_diagnostic_v1/catalog.json','outputs/research_archive/occam_performance_core_v1/catalog.json'),
    ('research_archive_build_occam_core_20261028_a37a003caef7','research_archive_build_occam_window_20261028_'+source[:12]),
    ('ARCHIVE_FILE_CATALOG_OCCAM_CORE_20261028.json','ARCHIVE_FILE_CATALOG_OCCAM_WINDOW_20261028.json'),
    ("'outputs/occam_performance_core/')","'outputs/occam_performance_core/','outputs/occam_window_host/')"),
    ('Archive standard OCCAM-related performance core and software verification; no robot results','Archive continuous performance host contract and complete retained reader failures; no learned task gain')):
    assert old in s,old;s=s.replace(old,new)
extra='''
def scan_record_parts():
    index_name='outputs/occam_window_host/delivery_v1/record_parts_index.json'
    raw=git('show',SOURCE+':'+index_name);index=json.loads(raw);io.require(index['integrity']=='PASSED','parts index')
    allowed=set();checks=[];seen=set()
    for artifact in index['artifacts']:
        original=artifact['original_path'];io.require(original.startswith('outputs/occam_window_host/native_v1/') and Path(original).name in ('cases.jsonl.gz','events.jsonl.gz','witnesses.jsonl.gz'),'owned original')
        io.require(original not in seen,'unique stream');seen.add(original)
        completion=json.loads(git('show',SOURCE+':'+str(Path(original).parent/'completion.json').replace('\\\\','/')))
        io.require(completion['artifact_sha256'][Path(original).name]==artifact['original_sha256'],'parts bind original collection completion')
        values=[]
        for part in artifact['parts']:
            name=part['path'];io.require(name.startswith('outputs/occam_window_host/delivery_v1/parts/') and name.endswith('.bin') and name not in allowed,'only owned unique bounded parts')
            data=git('show',SOURCE+':'+name);io.require(len(data)==part['bytes']<=4*1024**2 and hashlib.sha256(data).hexdigest()==part['sha256'],'actual Git part bytes')
            values.append(data);allowed.add(name)
        joined=b''.join(values);io.require(len(joined)==artifact['original_bytes'] and hashlib.sha256(joined).hexdigest()==artifact['original_sha256'],'actual complete gzip recovery')
        decoded=gzip.decompress(joined);io.require(len(decoded)==artifact['decoded_bytes'] and hashlib.sha256(decoded).hexdigest()==artifact['decoded_sha256'],'actual decoded stream hash')
        scan(decoded,original+'.decoded.json')
        checks.append(dict(original_path=original,original_sha256=artifact['original_sha256'],parts=len(values),decoded_bytes=len(decoded),decoded_sha256=artifact['decoded_sha256'],actual_git_recovery_and_full_decoded_scan=True))
    io.require(len(checks)==3 and len(allowed)==5,'all three streams and five parts')
    return allowed,dict(index_sha256=hashlib.sha256(raw).hexdigest(),artifacts=checks)

'''
assert '\ndef main():' in s;s=s.replace('\ndef main():','\n'+extra+'def main():',1)
needle="    baseline_path=ROOT/";i=s.index(needle);s=s[:i]+"    allowed_parts,record_parts_scan=scan_record_parts()\n"+s[i:]
old="not name.endswith(('.jsonl.gz','.bin')) or (name.startswith("
assert old in s;s=s.replace(old,"not name.endswith(('.jsonl.gz','.bin')) or name in allowed_parts or (name.startswith(",1)
old="prior_catalog_sha256=io.sha(baseline_path),all_source_files=len(catalog)"
assert old in s;s=s.replace(old,"prior_catalog_sha256=io.sha(baseline_path),decoded_record_parts=record_parts_scan,all_source_files=len(catalog)",1)
i=s.index("    note=f'''");j=s.index('    extras={',i)
note=f'''# 最新归档：OCCAM相关连续表现窗口原生主机资格

本地来源 {source}，冻结9087199，读者修复1d49623/b623f39，父归档{parent}。
完整36项构造模型人口仅采集一次：4203控制步、36受控重置、1836全部重置、
939015物理帧、3845次政策查询、142次在线滤波；33/36成功，全部3失败保留。
14对到达选择，首个实际命令全部不同；4对提前结束保留。世界/噪声/时钟、
保存决策消费、独立标量完整成本与联合高斯后验、完整人口/见证核对通过。

这是未训练构造模型的软件执行资格，不是完整OCCAM复现、科学任务优势或新算法。
31主机+4人口循环新增唯一检查，旧2487源码绑定复用，共2522。首次21项开发
未运行时计数的限制保留，后续守卫明确；无新科学离线训练/Adam/在线LLM。
标准势差只保证全段核账一致，不能保证短时贪心、预测或控制安全。

v1缺全局导入，v2配对覆盖流游标，两次失败和费用都保留；v3在4项完整人口
循环回归后另冻，只修导入/变量名，门槛/原始记录/科学源不变，零物理重跑。
先前滤波推算33漏计末段，更正34；实测/推得和缺失耗时分列，不能只报通过那次。
完整报告reports/occam_window_host_v1_zh.md，来源/成本/原始完整分母可追溯。

三原始gzip以五个<=4MiB分片完整保存。归档器从实际Git对象拼接每一组，
校验原采集completion SHA及完整解压字节后秘密扫描，才允许这些特定bin发布；
原始大文件/超限gzip副本留本地。旧省略目录维持，不把紧凑归档冒称全历史备份。
下一步仍需独立TRAIN/CAL/自身历史任务协议、强对照/消融与新机制验证；
独立任务优势和CCF A目标未完成。普通快进，无强推、合并或删除。
'''
tail='\n完整本地源树{len(catalog)}项，发布{sum(r["published"] for r in catalog)}项；完整省略目录保留。\n'
s=s[:i]+"    note=f'''"+note+tail+"'''\n"+s[j:];compile(s,'archive_checkpoint.py','exec');(out/'archive_checkpoint.py').write_bytes(s.encode('utf8'))
p=(ROOT/'outputs/research_archive/occam_performance_core_v1/push_occam_core_archive_v1.py').read_text('utf8').replace('outputs/research_archive/occam_performance_core_v1','outputs/research_archive/occam_window_host_v1')
(out/'push_occam_window_archive_v1.py').write_bytes(p.encode('utf8'));print(source)
