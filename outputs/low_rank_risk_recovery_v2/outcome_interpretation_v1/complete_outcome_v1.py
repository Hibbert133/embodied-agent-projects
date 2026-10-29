"""Explain the frozen negative result from saved statistics, no new inference."""
from pathlib import Path
from fractions import Fraction
import sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(ROOT/'outputs/low_rank_risk_recovery_v2/tools'))
import run_saved_v2 as s
r=s.r
sys.path.insert(0,str(ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    out=s.BASE/'outcome_interpretation_v1';out.mkdir(exist_ok=False)
    (out/'complete_outcome_v1.py').write_bytes(Path(__file__).read_bytes())
    prior=r.read(s.BASE/'presentation_v1/delivery_validation.json')
    r.need(prior['integrity']=='PASSED_LOW_RANK_SAVED_RECOVERY_RESULT_DELIVERY','complete prior delivery')
    stats=r.read(s.OUT/'statistics.json');programs=stats['programs'];main=programs['RBF_RR2'];cheap=programs['FIXED_00']
    r.need(not stats['necessary_development_point_condition'],'frozen negative decision, no secondary promotion')
    rows=r.read(s.OUT/'selected_factual_outcomes.json');sums={n:sum(x['loss'] for x in rows if x['model']==n) for n in programs}
    for n,v in programs.items():r.need(abs(float(Fraction(sums[n],54))-v['mean_deadline_loss'])<1e-10,'all exact totals')
    doc=ROOT/'docs/research/low_rank_risk_pilot_outcome_v1_zh.md';r.need(not doc.exists(),'new interpretation only')
    names=['RBF_RR2','RBF_FULL','RBF_PCA2','RBF_RAW_RR3','TASK_BOUNDARY_MEAN',*('FIXED_'+str(i).zfill(2) for i in range(4))]
    lines=['# 低秩开发负结果：解释与A主线后续边界','',
        '**事后描述性分析；不调整已冻结模型、门或比较。**','',
        '预定主候选RBF_RR2未通过完整开发人口的必要点条件，封存这一版。它略优于全秩RBF，却劣于普通PCA、同总秩RAW_RR3、训练组任务时点均值及便宜固定策略。不能只报相对全秩的微小改善，也不能改选RR1或另一个核／秩。','',
        '|程序|含义|成功/54|完整平均损失|','|---|---|---:|---:|']
    meanings={'RBF_RR2':'RBF核；保留共同难度；预测成本差限2维','RBF_FULL':'同特征、核、权重和正则的全秩风险预测',
        'RBF_PCA2':'用标签PCA的2个成本差方向替换预测方向','RBF_RAW_RR3':'全成本限3维；与RR2加共同方向总秩匹配',
        'TASK_BOUNDARY_MEAN':'只用训练组的同任务、同边界平均成本'}
    for i,t in enumerate((.125,.5,2.,8.)):meanings['FIXED_'+str(i).zfill(2)]=f'CONTINUE；固定T={t:g}，沿用现有控制器定义'
    for n in names:lines.append(f'|{n}|{meanings[n]}|{programs[n]["success"]}/54|{float(Fraction(sums[n],54)):.6f}|')
    lines+=['','主候选的精确总损失为'+str(sums['RBF_RR2'])+'；固定CONTINUE/T=.125为'+str(sums['FIXED_00'])+
        '，差'+str(Fraction(sums['RBF_RR2']-sums['FIXED_00'],54))+'步／单位。费用已含真实前缀、获取与后继，失败计500，没有重复加获取。',
        'T在现有程序中控制积分纠正的力度／时间尺度，具体数值定义仍以原执行器为准；本试验没有修改它。','',
        '|全部任务|主候选成功/18|主候选损失|固定CONTINUE/.125损失|','|---|---:|---:|---:|']
    for task in r.core.TASKS:
        a=main['tasks'][task];b=cheap['tasks'][task]
        lines.append(f'|{task}|{a["success"]}/18|{a["mean_loss"]:.6f}|{b["mean_loss"]:.6f}|')
    lines+=['','|全部组|RBF_RR2|固定CONTINUE/.125|差步|','|---:|---:|---:|---:|']
    for g in range(9):
        a=main['group_means'][str(g)];b=cheap['group_means'][str(g)]
        lines.append(f'|{g}|{a:.6f}|{b:.6f}|{a-b:+.6f}|')
    lines+=['','完整18个任务／条件／边界格在主报告；全部31程序的558格、279逐组行和39条来源任务失败另存，不删push或某个组来改变结论。九个折的训练集重叠，不能将折或时间步称为独立验证样本。','',
        '|48/54有效PRE上的预测|完整向量归一化MSE|成本差归一化MSE|','|---|---:|---:|']
    for n in ('RBF_RR2','RBF_FULL','RBF_PCA2','RBF_RAW_RR3'):
        v=programs[n]['factual_prediction'];lines.append(f'|{n}|{v["full_vector_normalized_MSE"]:.9f}|{v["contrast_normalized_MSE"]:.9f}|')
    counts=main['selected_program_counts'];c=[sum(counts[str(i)] for i in range(k,k+4)) for k in (0,4,8)]
    lines+=['',f'主候选实际48个决策中选择CONTINUE {c[0]}、VALIDATE8 {c[1]}、MOVE_MEASURE {c[2]}；另6个提前结束不作模型选择。相对全秩的MSE改善及略低完整损失，没有变成对便宜固定策略的竞争力。预测误差、数值合法、完整收益必须分开。',
        '同获取T=.5的配对来源：主候选11个不利、15个改善、28个相等，完整分母54；不利严重度102步、改善309步，没有成功转失败／失败转成功。它们不是额外独立样本，不能据此判定期望因果有害更新率，或把整体劣势唯一归因为过多获取、模型失配或噪声。',
        '支持的判断：这一固定小数据标准低秩版本没有达到预定开发要求。反证：相对全秩数值有少量改善、部分次要秩更好，因此不能外推所有低秩方法均无效。无法区分的原因包括特征／核不足、旧源覆盖与样本量、任务相关排序难度和不同获取后的状态变化；本分析不为这些原因下唯一因果结论。','',
        '后续继续A，但不围绕本版加门控、改秩、补样本或从旧QUAL找阈值。下一机制必须具体说明：纠正改变状态与动作后，哪些模型结论仍可复用、哪些区域失效，以及为此付出验证／获取成本如何带来可检验的有限资源优势。需先与标准模型适用范围、完整风险／DR、简单重加权／局部重估、任务相关获取和已有联合测试处置比较；现有状态耦合算子构造本身也不是创新。',
        '在上述区别、来源覆盖及可证伪条件明确前，不启动新的机器人采集。以后独立训练、校准和自身历史任务评价须另冻结，并保留DIRECT_C8、积分、始终获取／不更新、变化检测与历史辨识等强对照。标准RRR、成本平移不改排序或本次负结果都不能替代CCF A贡献。','']
    # The T label is left at its frozen definition; do not invent an online
    # controller interpretation in a post-hoc summary.
    lines=[line for line in lines if not line.startswith('T在现有程序中控制')]
    with doc.open('x',encoding='utf-8',newline='\n') as stream:stream.write('\n'.join(lines))
    r.write(out/'receipt.json',dict(integrity='PASSED_SAVED_STATISTICS_ONLY_NEGATIVE_INTERPRETATION',
        statistics_sha256=r.sha(s.OUT/'statistics.json'),all_31_exact_totals_checked=True,main_total_loss=sums['RBF_RR2'],
        cheap_total_loss=sums['FIXED_00'],primary_fixed=True,new_fits=0,new_predictions=0,new_source_graph_parses=0,counters=r.ZERO))
    owned=set(r.git('diff','--cached','--name-only').decode().splitlines())
    owned.add(doc.relative_to(ROOT).as_posix());owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file())
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');r.write(out/'index_disk_proof.json',dict(integrity='PASSED_RESULT_PLUS_INTERPRETATION_INDEX',objects=check_index(owned)))
    owned.update(p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(dict(integrity='PASSED_READY_FOR_FULL_RESULT_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values())),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
