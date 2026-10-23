"""Chinese evidence report; no new fitted model, threshold, or controller."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import observable_history_io_v1 as io
from scripts.analyze_history_response_failure_v1 import SOURCE,OUTPUT

NAMES=("HISTORY_LINEAR10","STATE_LINEAR20","QUADRATIC_STATE20","GRU_WINDOW1","GRU_WINDOW16","ZERO_DISPLACEMENT","LAST_DISPLACEMENT")


def f(x,scale=1):return "缺失" if x is None else f"{x*scale:.6g}"


def report(output=OUTPUT):
    completion=io.read(output/"completion.json");audit=io.read(output/"independent_audit.json");io.require(audit["integrity"]=="PASSED","independent audit before report")
    io.require(io.sha(output/"completion.json")==audit["completion_sha256"],"analysis changed")
    tables=io.read(output/"grouped_tables.json");features=io.read(output/"feature_tables.json");bank=io.read(SOURCE/"training/models.json")["models"];original=io.read(SOURCE/"evaluation/statistics.json")
    def overall(split,name,stage="POST_TASK"):return next(r for r in tables["overall"] if (r["split"],r["method"],r["stage"])==(split,name,stage))
    def match(task,source,name,stage):return next(r for r in tables["matched_training"] if (r["task"],r["source_bank"],r["method"],r["stage"])==(task,source,name,stage))
    text=["# 历史响应模型资格失败：零交互诊断报告 v1", "", "**全部新增分析均为事后描述性分析。原资格仍为NOT_QUALIFIED。**",
        "本轮读取全部756次执行和30个保存模型，没有重训、改尺度、改窗口、补样本、执行新控制或调用在线LLM。数值合法性、预测能力、含获取成本的任务收益分别判断。", "",
        f"来源：`{completion['source_run_id']}`；来源结果提交`{completion['source_result_commit']}`；诊断实现提交`{completion['analysis_git_commit']}`。", "",
        "## 原结果和新问题", "",f"原主差GRU16−GRU1为{f(original['primary_difference'],1000)} mm，原95%整组区间为{[1000*x for x in original['primary_group_bootstrap_95']]} mm；主响应可用364/432、18组、24格均保留。GRU16仍在全部24格劣于两条线性参考。",
        "本轮问：模型是否连匹配TRAIN都没拟合好；训练目标是否被不同阶段主导；公开输入标准化后是否偏移或导致门饱和；原误差与外加噪声有什么描述性关系。任何一个统计量都不能认定唯一物理原因。", "",
        "## 首要诊断结论", ""]
    train_bad=0
    for task in io.TASKS:
        for source in io.PROGRAMS:
            v=[match(task,source,n,"POST_TASK")["rmse"] for n in ("GRU_WINDOW16","HISTORY_LINEAR10","STATE_LINEAR20")]
            train_bad+=all(x is not None for x in v) and v[0]>max(v[1:])
    nominal=[r for r in tables["task_context_program"] if r["split"]=="CAL" and r["context"]=="NOMINAL" and r["stage"]=="POST_TASK"]
    nominal_bad=0
    for task in io.TASKS:
        for program in io.PROGRAMS:
            values={r["method"]:r["rmse"] for r in nominal if r["task"]==task and r["measurement_program"]==program}
            nominal_bad+=all(values[n] is not None for n in ("GRU_WINDOW16","HISTORY_LINEAR10","STATE_LINEAR20")) and values["GRU_WINDOW16"]>max(values["HISTORY_LINEAR10"],values["STATE_LINEAR20"])
    text += [f"匹配TRAIN任务尾段的6个任务/来源格中，GRU16有{train_bad}/6格劣于两条线性参考；独立名义CAL的6个任务/程序格中有{nominal_bad}/6格劣于两条线性参考。名义CAL没有边界扰动改变，若其误差已恶化，不能把改变条件当作必要触发因素。",
        f"原TEST尾段的固定零位移预测误差为{f(overall('TEST','ZERO_DISPLACEMENT')['rmse'],1000)} mm，最近位移预测为{f(overall('TEST','LAST_DISPLACEMENT')['rmse'],1000)} mm；原历史线性为{f(overall('TEST','HISTORY_LINEAR10')['rmse'],1000)} mm。这两个新参考只有描述用途，不改变原资格门槛，也不是机器人停止/保持控制器。",
        "GRU1与GRU16使用相同43维输入、初始化和采样日程，支持在这一固定训练过程内比较历史长度。它们与10/20维线性模型同时存在特征、容量和优化差异，不能将跨家族误差差异唯一归因于历史、网络容量或训练不足。", "",
        "## 匹配TRAIN：完整拟合与任务尾段", "", "单位mm。每轨迹内计算，再按组等权；只有来源匹配的原TRAIN，避免把跨程序预测误称训练拟合。", "",
        "|任务|训练来源|阶段|可用轨迹/36|历史线性|状态线性|二阶|GRU1|GRU16|零位移|最近位移|", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for task in io.TASKS:
        for source in io.PROGRAMS:
            for stage in ("ALL_RESPONSE","POST_TASK"):
                rs=[match(task,source,n,stage) for n in NAMES];text.append(f"|{task}|{source}|{stage}|{rs[0]['available_cells']}|"+"|".join(f(r["rmse"],1000) for r in rs)+"|")
    text += ["", "## 原优化目标及末次批次", "", "完整TRAIN标准化误差按原轨迹等权、轨迹内均匀目标复算。末次批次记录在最后一次更新前，完整误差使用保存权重；二者差异不能单独证明未收敛。", "",
        "|任务|来源|窗口|末批标准化MSE|完整TRAIN标准化MSE|探测目标质量|移动目标质量|测量目标质量|尾段目标质量|", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for task in io.TASKS:
        for source in io.PROGRAMS:
            for name in ("GRU_WINDOW1","GRU_WINDOW16"):
                m=bank[source][task][name];mass=[match(task,source,name,s)["optimization_sampling_mass"] for s in ("FIXED_PROBE","MOVEMENT_ALL","MEASUREMENT","POST_TASK")]
                text.append(f"|{task}|{source}|{m['window']}|{f(m['loss_checkpoints'][-1]['standardized_train_batch_mse'])}|{f(match(task,source,name,'ALL_RESPONSE')['standardized_mse'])}|"+"|".join(f(x) for x in mass)+"|")
    text += ["", "阶段优化误差贡献和采样质量可在grouped_tables.json中复算；排他阶段的贡献之和等于完整目标。空阶段的加和质量为0，阶段预测误差仍缺失；没有把不存在的响应填成零。表内阶段质量未列PRE_BOUNDARY，因此四列不要求加和为1。", "",
        "## 来源×部署程序的全部四格", "", "以下保留三个划分及两训练来源×两部署程序。TRAIN中非匹配程序的误差是跨程序描述。单位mm。", "",
        "|划分|训练来源|部署程序|可用源轨迹|历史线性|状态线性|二阶|GRU1|GRU16|零位移|最近位移|", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for split in io.SPLITS:
        for source in io.PROGRAMS:
            for program in io.PROGRAMS:
                rs=[next(r for r in tables["source_program_transfer"] if (r["split"],r["source_bank"],r["measurement_program"],r["method"],r["stage"])==(split,source,program,n,"POST_TASK")) for n in NAMES]
                text.append(f"|{split}|{source}|{program}|{rs[0]['available_cells']}/{rs[0]['allocated_cells']}|"+"|".join(f(r["rmse"],1000) for r in rs)+"|")
    text += ["", "## 当前输入范围与门描述", "", "仅为描述性比例，不是阈值或安全保证。标准化使用保存的TRAIN统计；范围由原匹配TRAIN的当前t≥2输入构建。真实最早两帧不在该范围估计参考中，本表也只描述当前帧。", "",
        "下表完整列出GRU16在两个关键阶段、各任务/上下文/程序的结果；两个训练来源等权。全部阶段和43维数值另见诊断记录与feature_tables.json。", "",
        "|划分|任务|上下文|程序|阶段|可用单元|平均最大abs(z)|任一abs(z)>10比例|超TRAIN范围比例|更新门饱和|候选饱和|", "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in tables["task_context_program"]:
        if r["method"]=="GRU_WINDOW16" and r["stage"] in ("ALL_RESPONSE","POST_TASK"):
            text.append(f"|{r['split']}|{r['task']}|{r['context']}|{r['measurement_program']}|{r['stage']}|{r['available_cells']}/{r['allocated_cells']}|"+"|".join(f(r[k]) for k in ("gru_current_input_max_abs_z_mean","gru_current_input_any_abs_z_over_10","gru_current_input_any_outside_train_range","gru_update_saturated","gru_candidate_saturated"))+"|")
    text += ["", "小标准差可以放大偏移，但范围外比例、饱和比例和误差的共同出现不是唯一因果解释。不同任务可能存在不同问题；也须考虑特征选择、正则化、阶段目标权重和一次固定初始化。没有用旧TEST试新尺度或屏蔽维度。", "",
        "## 43维完整输入附表", "", "每个来源/任务列出全部43维。值为当前帧绝对z的轨迹内.95分位数，再在组内和组间平均；三个划分均使用匹配部署程序的POST_TASK。未知维度只按原始索引命名，不凭猜测解释其物理角色。", "",
        "|任务|来源|公开输入索引|原TRAIN尺度|TRAIN abs(z).95|CAL abs(z).95|TEST abs(z).95|TEST超范围比例|TEST单维仿射RMS贡献|", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for task in io.TASKS:
        for source in io.PROGRAMS:
            cells={split:next(r for r in features if (r["split"],r["task"],r["source_bank"],r["measurement_program"],r["stage"])==(split,task,source,source,"POST_TASK")) for split in io.SPLITS}
            for j in range(43):
                feature=f"obs[{j}]" if j<39 else f"sent_command[{j-39}]";values=[None if cells[s]["feature_abs_z_q95"] is None else cells[s]["feature_abs_z_q95"][j] for s in io.SPLITS]
                test=cells["TEST"];extra=[None if test[k] is None else test[k][j] for k in ("feature_outside_train_fraction","feature_input_affine_rms_contribution")]
                text.append(f"|{task}|{source}|{feature}|{f(bank[source][task]['GRU_WINDOW16']['input_scale'][j])}|"+"|".join(f(x) for x in (*values,*extra))+"|")
    text += ["", "单维仿射贡献为该维标准化输入乘输入权重列的RMS，不包含偏置与维度间抵消，不能把这些正数相加作为总预测误差的归因。", "",
        "## 原始外加噪声与误差", "", "原始噪声仅用于评价。以下为每轨迹相关后按组平均，空/常量/不足3对为缺失；不对相关时间步计算独立样本p值。滞后1/2及全部XY/XYZ矩阵保存在完整诊断中。", "",
        "|划分|模型|阶段|误差X-噪声X lag0|误差Y-噪声Y lag0|误差X自相关lag1|误差Y自相关lag1|", "|---|---|---|---:|---:|---:|---:|"]
    for split in io.SPLITS:
        for name in ("HISTORY_LINEAR10","STATE_LINEAR20","GRU_WINDOW1","GRU_WINDOW16"):
            for stage in ("ALL_RESPONSE","POST_TASK"):
                r=overall(split,name,stage);text.append(f"|{split}|{name}|{stage}|"+"|".join(f(r[k]) for k in ("noise_x_lag0","noise_y_lag0","residual_x_lag1","residual_y_lag1"))+"|")
    text += ["", "相关可支持噪声影响或误差时间结构，但不识别唯一估计偏差、物理接触或噪声下界。输入先仿射/死区，再XYZ噪声和最终裁剪；不能用残差相关替代该链的物理辨识。", "",
        "## 全任务、条件、程序、阶段误差附表", "", "下表完整保留全部阶段。单位mm；两个训练来源先在同轨迹等权，不是两次独立机器人重复。可用单元列为轨迹×来源单元数；实际轨迹数为其一半。", "",
        "|划分|任务|条件|程序|阶段|可用/分配|历史线性|状态线性|二阶|GRU1|GRU16|零位移|最近位移|", "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    index={tuple(r[k] for k in ("split","task","context","measurement_program","stage","method")):r for r in tables["task_context_program"]}
    keys=sorted({key[:-1] for key in index})
    for key in keys:
        rows=[index[(*key,n)] for n in NAMES];r=rows[0];text.append("|"+"|".join(key)+f"|{r['available_cells']}/{r['allocated_cells']}|"+"|".join(f(r["rmse"],1000) for r in rows)+"|")
    text += ["", "## 后续判断与研究边界", ""]
    if train_bad>=3:text.append("当前优先检查独立训练资格与输入表示，匹配TRAIN尾段已出现广泛劣化。直接增加真实交互、历史长度或接受规则缺少依据。应先在单列的开发协议中区分优化目标、特征和容量，冻结前置条件后再考虑新采集。")
    else:text.append("当前更需要区分训练内拟合与跨轨迹/程序迁移。应在独立设计中保持同一可见特征和目标，分离输入几何、历史长度、容量及残差锚定；未通过匹配开发/校准资格前，不开展新控制采集。")
    text += ["本轮不训练新变体，不让失败的GRU或ARX进入逆控制/获取选择器。单步预测好也不证明逆映射适当或任务收益；强线性工作模型的控制相关性仍须在另行冻结、含全部获取成本的任务试验中验证。",
        "论文主线仍是物理状态持续变化、模型可能失配时的获取—采用决策，需要新方法自身的独立历史、DIRECT_C8/积分/始终获取/不更新/标准变化检测/历史辨识/任务相关获取强参考及消融。通用残差网络、历史编码或价值分解本身不是新贡献；本诊断与测试通过不代表CCF A目标完成。", "",
        "## 复算、来源与成本", "",f"核对全部{completion['executions']}例、{completion['source_physical_steps']}个历史源步、{completion['common_real_responses']}条共同响应；原TEST {completion['source_TEST_predictions_unchanged']}个预测和{completion['source_TEST_stage_metrics_unchanged']}个指标保持不变。独立审计重建{audit['trajectory_stage_model_cells_checked']}个轨迹/阶段/模型单元及全部门/输入描述。",
        f"新增环境创建/控制步/重置/物理帧/在线LLM API/模型拟合/参数变体均为0。分析纯计算{completion['wall_ns']/1e9:.3f}秒，独立审计{audit['wall_ns']/1e9:.3f}秒。来源完整费用保留在原cost_audit.json：756次/71773控制步/38556全部重置/19636865帧、30模型、60000更新；既有C8及旧响应来源另列，不重复计费。",
        "源码、源结果、原始gzip、模型和统计的SHA256见source_hashes.json及completion.json。全过程没有修改来源。新增17项测试仅用纯数组；旧1489项回执对应源码哈希复核后沿用，未重复原生仿真夹具。", ""]
    target=ROOT/"reports/history_response_failure_analysis_v1_zh.md"
    with target.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(text))
    io.write(output/"report_receipt.json",{"report":target.relative_to(ROOT).as_posix(),"sha256":io.sha(target),"new_environment_steps":0,"new_api_calls":0,"new_model_fits":0})
    print(target);return target


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=OUTPUT);report(parser.parse_args().output.resolve())
