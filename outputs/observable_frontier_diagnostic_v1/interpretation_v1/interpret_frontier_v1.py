"""Read saved classes only; distinguish equal cost from equal information sets."""
from pathlib import Path
from fractions import Fraction
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(ROOT/'outputs/observable_frontier_diagnostic_v1/tools'))
import run_frontier_v1 as r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    r.need(r.read(r.BASE/'presentation_v1/delivery_validation.json')['integrity']=='PASSED_OBSERVABLE_FRONTIER_RESULT_DELIVERY','completed base delivery')
    out=r.BASE/'interpretation_v1';out.mkdir(exist_ok=False);(out/'interpret_frontier_v1.py').write_bytes(Path(__file__).read_bytes())
    result=r.read(r.OUT/'empirical_frontier.json');s=r.read(r.OUT/'statistics.json')
    panels={(p['root_sha256'],p['acquisition_index'],p['mode']):p for p in result['return_panels']};pairs=[]
    for root,a,mode in panels:
        if mode!='FULL':continue
        full=panels[root,a,'FULL'];mask=panels[root,a,'MASK']
        partition=lambda p:sorted(tuple(c['members']) for c in p['return_classes'])
        r.need(full['terminal_members']==mask['terminal_members'],'same actually terminated population')
        pairs.append(dict(root_sha256=root,acquisition_index=a,full_classes=len(full['return_classes']),mask_classes=len(mask['return_classes']),
            exact_partitions_equal=partition(full)==partition(mask),terminal_members=full['terminal_members']))
    r.need(len(pairs)==3*s['root_count'],'all root/acquisition pairs')
    different=sum(not p['exact_partitions_equal'] for p in pairs)
    counts={n:{str(a):sum(q['functional']==n and q['chosen_acquisition_index']==a for q in result['records']) for a in (None,0,1,2)}
        for n in ('ROOT_CONTINUE_ONLY','ROOT_STATIC','ROOT_ADAPTIVE_FULL','ROOT_ADAPTIVE_MASK')}
    r.write(out/'all_root_acquisition_partition_pairs.json',pairs)
    r.write(out/'receipt.json',dict(integrity='PASSED_SAVED_PARTITION_EQUALITY_SUPPLEMENT',root_acquisition_pairs=len(pairs),different_partitions=different,
        all_returns_including_termination_retained=True,chosen_acquisition_counts=counts,source_analysis_sha256=r.sha(r.OUT/'complete.json'),
        new_original_graph_parses=0,new_predictions_or_fits=0,uses_future_labels=True,deployable=False,counters=r.ZERO))
    doc=ROOT/'docs/research/observable_frontier_outcome_v1_zh.md';r.need(not doc.exists(),'new outcome brief')
    static=s['functionals']['ROOT_STATIC']['total_loss'];full=s['functionals']['ROOT_ADAPTIVE_FULL']['total_loss'];cont=s['functionals']['ROOT_CONTINUE_ONLY']['total_loss']
    text=f'''# A主线：公开信息事实诊断之后的决定

2026-10-29。全部为旧TRAIN事后描述性分析，使用未来结局的最优表不可部署。
48个有效单位形成24个精确公开根类；另外6个提前结束保留在54分母。
4个根类存在单位最优叶冲突，相同公开根的静态约束总计损失23步，不能
据此推出未知分布的不可识别性界或可学习性结论。

根静态表总成本{static}（均值{float(Fraction(static,54)):.6f}），实际返回后
选择T的FULL表{full}（均值{float(Fraction(full,54)):.6f}），总计只少
{static-full}步，即每单位{float(Fraction(static-full,54)):.6f}步。原始分支的
前缀、获取、后继及失败500惩罚都已包含一次。此处说的是对固定T选择的
经验增量；两个表中的固定T底层控制器仍在每一步读取真实反馈并更新积分，
根静态绝不等于开环、屏蔽反馈或完全不利用新信息。

FULL与MASK经验最优成本相同，单凭成本相等本来不能推出信息分组相同。
另一次读取保存分组的补充核对覆盖全部{len(pairs)}个根×获取组合，分组不同
{different}个；终止成员也一致。这个额外事实只针对当前完整记录。MASK仍有
实际返回当前观测／积分／时钟／控制器及全部根历史，连续唯一返回可让
未来表记忆。不能据此说额外轨迹在未知分布无信息或学习接收者不需要历史。

根静态与只允许继续T的表之间总差为{cont-static}步，说明此菜单仍有获取
分支的记录差异；其中也可能有获取过程的任务推进和后继反馈作用。没有
随机隔离自然信息／物理效应，不能把这个差额命名为纯信息收益。

## 已接受与封存的决定

- 保持A与完整CCF A目标；旧低秩及所有既有接收者负结果不变。
- 关闭“在此旧菜单中反复改返回后T选择器就有大额信息增益”的经验动机；
  不再围绕这一固定菜单拟合新门、调整核／秩／精度、筛任务或扩旧样本。
- 这不是所有主动获取或A的否定。该经验表会记忆未来，不能说实际模型
  能达到{float(Fraction(full,54)):.6f}，也不能把它与107的差唯一归因为拟合错误。
- 下一机制需明确纠正如何改变模型的适用条件，而不是只把固定T选择
  换成更复杂预测器。原状态相关算子仅为DESIGN_ONLY、没有新物理人口。
  任何新实例须保留平坦端点和同权限MDE／动态前瞻／完整风险、简单局部
  重估／重加权等强参考；不能靠挑边界或加偏置制造优势。
- 在具体结构／可证伪区别和独立训练、校准、自身时序任务预算明确前，
  不启动新机器人采集。诊断的未来表不用作训练标签，不替代最终强对照、
  失败案例、交互成本、消融及独立收益。

本轮15项构造检查、主分解求解与独立1560条件计划穷举、972事实引用、
全部162组行／324分格、39来源任务失败都保留。新环境／预测模型查询
或拟合／在线LLM为0，365个经验表argmin与1996候选值比较另列。纯标准
计算和审计通过不代表论文贡献。
'''
    with doc.open('x',encoding='utf-8',newline='\n') as stream:stream.write(text)
    report=ROOT/'reports/observable_frontier_diagnostic_v1_zh.md'
    with report.open('ab') as stream:stream.write(('\n## 补充：信息分组与固定T反馈边界\n\n'+
        f'成本相等本身不能推出信息类相等。另对全部{len(pairs)}个根×获取组合逐成员核对，FULL与MASK分组不同{different}个，终止成员也相同。仅对这批精确记录成立，不证明未知分布的信息无用。根静态固定的是获取及T，原底层策略与积分仍逐步接收真实反馈；1步总差只是返回后改T的额外经验价值。\n\n'+
        '后续判断见[决定简报](../docs/research/observable_frontier_outcome_v1_zh.md)，旧菜单不再靠改接收者／门／精度救活；A的具体新机制、独立自身历史收益及CCF A目标仍未建立。\n').encode('utf-8'))
    owned=set(r.git('diff','--cached','--name-only').decode().splitlines())
    owned.add(doc.relative_to(ROOT).as_posix());owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file())
    def stage(label):
        p=out/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');r.write(out/'index_disk_proof.json',dict(integrity='PASSED_RESULT_AND_INTERPRETATION_INDEX',objects=check_index(owned)))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_COMPLETE_FRONTIER_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values())),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
