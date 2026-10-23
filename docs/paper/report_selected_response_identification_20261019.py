"""Chinese delivery from closed, independently audited records; no new fitting."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/"outputs/reproduction_reviews/selected_response_identification_v1/analysis_v1"
REPORT = ROOT/"reports/selected_response_identification_v1_zh.md"
TASKS = {"push-v3":"推物","reach-v3":"到达","door-open-v3":"开门"}
METHODS = ("SELECTED_INPUT_ONLY","SELECTED_HISTORY","SELECTED_POSE_HISTORY","SAVED_C8","RELOCATION_INTEGRAL")
LABELS = ("只看输入","输入＋历史","位置＋历史","旧C8","移动积分")
IDENTITY = ("experiment_run_id","manifest_id","source_git_commit")


def require(ok,message):
    if not ok:raise ValueError(message)


def read(path):return json.loads(path.read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write("\n")


def load_closed(path):
    """Refuse a running or partially audited study before reading its records."""
    path=path.resolve();run=path.parent
    require(path.is_relative_to((ROOT/"outputs/selected_response/qualification_v1").resolve()),"registered report source required")
    for name in ("train/completion.json","train_audit/record_audit.json","models_completion.json","models.json"):
        if not (run/name).exists():raise RuntimeError("Study not ready for a result report: missing "+name)
    manifest=read(path)
    canonical=json.dumps({k:v for k,v in manifest.items() if k!="manifest_id"},sort_keys=True,separators=(",",":"),allow_nan=False)
    require(hashlib.sha256(canonical.encode()).hexdigest()==manifest["manifest_id"],"manifest digest changed")
    require(manifest["config"]["protocol_id"]=="selected_response_identification_v1","wrong protocol")
    bindings={ROOT/k:v for k,v in manifest["input_sha256"].items()};bindings[path]=sha(path)
    def bound(name):
        p=run/name;bindings[p]=sha(p);return read(p)
    def identity(value):
        require(all(value[k]==manifest[k] for k in IDENTITY),"source identity differs")
    def collection(stage):
        done=bound(stage+"/completion.json");audit=bound(stage+"_audit/record_audit.json")
        identity(done);identity(audit)
        require(done["status"]=="COLLECTED_FOR_INDEPENDENT_AUDIT" and audit["integrity"]=="PASSED" and audit["stage"]==stage,"collection audit incomplete")
        require(done["artifact_sha256"]==audit["collection_artifact_sha256"],"collection binding differs")
        require(set(done["artifact_sha256"])=={"events.jsonl.gz","cases.jsonl.gz","state_witnesses.jsonl.gz","status.json","summary.json"},"incomplete collection artifacts")
        bindings.update({run/stage/k:v for k,v in done["artifact_sha256"].items()})
        require(audit["executions"]==len(manifest["config"][stage+"_cases"])==len(audit["rows"]),"missing population")
        return audit
    train=collection("train");bank=bound("models.json");done=bound("models_completion.json")
    identity(bank);identity(done)
    require(done["models_sha256"]==bindings[run/"models.json"] and done["status"]==bank["status"],"model completion differs")
    require(bank["train_audit_sha256"]==bindings[run/"train_audit/record_audit.json"] and bank["train_collection_sha256"]==train["collection_artifact_sha256"],"model TRAIN source differs")
    require(bank["training_costs"]==train["costs"] and bank["training_attempts"]==train["executions"],"training costs/counts differ")
    require([(r["task"],r["method"]) for r in bank["fits"]]==[(t,m) for t in TASKS for m in METHODS[:3]],"missing registered model fit")
    packet={"manifest":manifest,"train":train,"bank":bank,"qualify":None,"evaluation":None,"estimates":[],"numeric_audit":None}
    if bank["status"]=="FAILED_TRAIN_SUPPORT":
        require(not all(r["valid"] for r in bank["fits"]) and not (run/"qualify").exists(),"unsupported model cannot start qualification")
    elif bank["status"]=="READY_FOR_INDEPENDENT_QUALIFICATION":
        for name in ("model_audit/record_audit.json","qualify_audit/record_audit.json","evaluation/summary.json","evaluation_audit/record_audit.json"):
            if not (run/name).exists():raise RuntimeError("Study not ready for a result report: missing "+name)
        models_audit=bound("model_audit/record_audit.json");identity(models_audit)
        require(models_audit["integrity"]=="PASSED" and models_audit["models_sha256"]==done["models_sha256"],"model audit differs")
        qualify=collection("qualify");summary=bound("evaluation/summary.json");audit=bound("evaluation_audit/record_audit.json")
        identity(summary);identity(audit)
        require(audit["integrity"]=="PASSED" and audit["evaluation_summary_sha256"]==bindings[run/"evaluation/summary.json"],"numeric audit differs")
        require(summary["models_sha256"]==done["models_sha256"] and summary["qualification_audit_sha256"]==bindings[run/"qualify_audit/record_audit.json"],"evaluation source differs")
        require(audit["cases"]==qualify["executions"],"numeric audit population differs")
        estimate_path=run/"evaluation/estimates.jsonl";bindings[estimate_path]=summary["estimates_sha256"]
        with estimate_path.open(encoding="utf-8") as handle:rows=[json.loads(line) for line in handle]
        require(len(rows)==qualify["executions"],"missing estimates")
        packet.update(qualify=qualify,evaluation=summary,estimates=rows,numeric_audit=audit)
    else:raise ValueError("unrecognized model outcome")
    for p,value in bindings.items():require(sha(p)==value,"bound artifact changed: "+str(p))
    return packet,bindings


def training_table(rows):
    return [{"task":task,"boundary":boundary,"attempts":sum(r["task"]==task and r["planned_boundary"]==boundary for r in rows),
        "complete":sum(r["task"]==task and r["planned_boundary"]==boundary and r["complete_window"] for r in rows)}
        for task in TASKS for boundary in (16,32,64)]


def figures(packet,folder,*,fixture=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties,findfont
    font=findfont(FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.family":"Microsoft YaHei","axes.unicode_minus":False,"font.size":10})
    prefix="软件版式夹具｜非实验结果\n" if fixture else ""
    table=training_table(packet["train"]["rows"]);fig,axes=plt.subplots(1,3,figsize=(12,4.5),sharey=True)
    for ax,(task,label) in zip(axes,TASKS.items()):
        selected=[r for r in table if r["task"]==task]
        ax.bar(range(3),[r["complete"] for r in selected],color="#287e8e",label="完整窗口")
        ax.bar(range(3),[r["attempts"]-r["complete"] for r in selected],bottom=[r["complete"] for r in selected],color="#d1d8df",label="未获得完整窗口")
        for j,r in enumerate(selected):ax.text(j,r["attempts"]+.02*max(1,r["attempts"]),f"{r['complete']}/{r['attempts']}",ha="center")
        ax.set_xticks(range(3),["16步边界","32步边界","64步边界"]);ax.set_title(label);ax.grid(axis="y",alpha=.15);ax.set_axisbelow(True)
    axes[0].set_ylabel("预分配尝试数；标注为完整数/全部尝试")
    axes[0].set_ylim(0,max(r["attempts"] for r in table)*1.2)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="upper center",bbox_to_anchor=(.5,.84),ncol=2,frameon=False,fontsize=9)
    fig.suptitle(prefix+"名义训练：全部尝试与完整测量窗口",fontsize=14)
    fig.tight_layout(rect=(0,0,1,.79));paths=[folder/"nominal_attempts_zh.png"]
    fig.savefig(paths[-1],dpi=160);plt.close(fig)
    summary=packet["evaluation"]
    if summary is not None:
        fig,axes=plt.subplots(2,2,figsize=(13,8.5));colors=["#8c9eac","#4f8cab","#22766a","#ad8a55","#7f75a5"]
        ax=axes[0,0];values=[r["score"] for r in summary["methods"]]
        ax.bar(range(5),values,color=colors);ax.set_ylabel("全人口平均辨识分数（含不可用惩罚）")
        for j,v in enumerate(values):ax.text(j,v+.02*max(max(values),.1),f"{v:.3f}",ha="center",fontsize=9)
        ax.set_ylim(0,max(max(values),.1)*1.2)
        ax=axes[0,1];denominator=summary["methods"][0]["attempts"]
        ax.bar(range(5),[r["valid"] for r in summary["methods"]],color=colors)
        for j,r in enumerate(summary["methods"]):ax.text(j,r["valid"]+denominator*.025,f"{r['valid']}/{denominator}",ha="center",fontsize=9)
        ax.set_ylim(0,denominator*1.16);ax.set_ylabel("全人口有效估计数")
        for ax in axes[0,:]:ax.set_xticks(range(5),LABELS,rotation=15)
        ax=axes[1,0]
        for j,r in enumerate(summary["contrasts"]):
            lo,hi=r["ci95"];ax.hlines(j,lo,hi,color="#22766a",lw=2);ax.plot(r["mean_difference"],j,"o",color="#22766a")
            ax.text(lo,j+.14,f"[{lo:.3f}, {hi:.3f}]",fontsize=9)
        ax.axvline(0,color="#999999",ls="--");ax.set_yticks([0,1],["候选 − 输入＋历史","候选 − 移动积分"])
        ax.set_ylim(-.45,1.55);ax.set_xlabel("分数差与组重采样95%区间；负值有利于候选")
        ax=axes[1,1];fees=summary["costs"];units=fees["amortization_paired_units"];base=[0.]*5
        for key,label,color in (("online_steps","在线证据","#43889d"),("new_nominal_steps","完整新名义训练","#d7a25c"),("historical_steps","历史名义来源","#a4adb7")):
            values=[r[key]/units for r in fees["method_accounting"]]
            ax.bar(range(5),values,bottom=base,color=color,label=label);base=[x+y for x,y in zip(base,values)]
        ax.set_xticks(range(5),LABELS,rotation=15);ax.set_ylabel("控制步/配对单元（每单元两次执行）");ax.legend(fontsize=8)
        for ax in axes.flat:ax.grid(axis="y",alpha=.15);ax.set_axisbelow(True)
        fig.suptitle(prefix+"独立辨识：全部对照、区间及完整成本",fontsize=15)
        fig.text(.5,.015,"分数不是任务损失；有效估计不是任务成功。各方法成本账共享同一实际采集，不能相加。",ha="center",fontsize=10)
        fig.tight_layout(rect=(0,.045,1,.94));paths.append(folder/"identification_and_costs_zh.png")
        fig.savefig(paths[-1],dpi=160);plt.close(fig)
    return paths,font


def number(value):return "—" if value is None else f"{value:.4f}"


def markdown(packet,figure_paths):
    manifest=packet["manifest"];train=packet["train"];bank=packet["bank"];summary=packet["evaluation"]
    outcome="训练支持未通过，未启动独立辨识" if summary is None else ("辨识资格通过（仅此组件）" if summary["qualification"]=="QUALIFIED_IDENTIFICATION_ONLY" else "辨识资格未通过")
    text=["# 附近测量点响应模型：训练与独立辨识", "",f"**本轮结论：{outcome}。尚未验证估计后的任务收益，也没有新增LLM API调用。**","",
        "机器人收到向右移动的指令，却可能实际向右上方移动。本轮估计这种动作偏差；前三个模型使用同一批训练数据和新探测观测，区别在于考虑哪些输入信息。", "",
        "## 方法名字是什么意思", "",
        "|方法名|图表简称|使用的信息与作用|", "|---|---|---|",
        "|SELECTED_INPUT_ONLY|只看输入|在选定测量点，根据探测指令与实际观测的关系估计动作偏差。|",
        "|SELECTED_HISTORY|输入＋历史|再考虑进入测量点前最近的运动情况。这里的历史是运动记录，不是聊天记忆。|",
        "|SELECTED_POSE_HISTORY|位置＋历史|进一步考虑手部在什么位置，因为不同位置的运动响应可能不同。|",
        "|SAVED_C8|旧C8|沿用最初八步探测得到的估计，不用后续测量更新。|",
        "|RELOCATION_INTEGRAL|移动积分|使用移向测量点时累计得到的补偿；继承C8矩阵，只更新固定偏移。|", "",
        "SELECTED 指选定的测量位置。用于移向测量点的 PID 控制，会结合当前距离、运动变化和累计偏差调整指令；它不是上述响应模型的名字。", "",
        f"冻结提交：`{manifest['source_git_commit']}`；清单：`{manifest['manifest_id']}`。", "",
        "## 名义训练的全部尝试", "", "|任务|边界|完整窗口/预分配尝试|", "|---|---:|---:|"]
    for r in training_table(train["rows"]):text.append(f"|{TASKS[r['task']]}|{r['boundary']}|{r['complete']}/{r['attempts']}|")
    text += ["",f"![名义训练](../{figure_paths[0].relative_to(ROOT).as_posix()})","",
        "训练按预分配尝试数停止，未通过的尝试没有被补采替换。完整窗口可能受所执行动作影响，随机分配不消除这一筛选效应。", "",
        "|任务|模型|训练窗口|拟合返回有效|错误记录|", "|---|---|---:|---|---|"]
    for r in bank["fits"]:
        error="—" if r["error"] is None else (r["error"]["type"]+": "+r["error"]["message"]).replace("|","/").replace("\n"," ")
        text.append(f"|{TASKS[r['task']]}|{LABELS[METHODS.index(r['method'])]}|{r['training_windows']}|{'是' if r['valid'] else '否'}|{error}|")
    if summary is None:
        text += ["","上述状态是冻结拟合程序的返回结果。没有通过独立数值审计的完整九模型组，因此没有验证集误差、资格区间或任务收益数据。"]
    else:
        text += ["","## 独立辨识结果","","|方法|有效/全部|全人口分数|仅有效估计的矩阵误差|仅有效估计的偏移误差|","|---|---:|---:|---:|---:|"]
        for r in summary["methods"]:
            text.append(f"|{LABELS[METHODS.index(r['method'])]}|{r['valid']}/{r['attempts']}|{number(r['score'])}|{number(r['valid_only_means']['matrix_error'])}|{number(r['valid_only_means']['bias_error'])}|")
        text += ["","分数为矩阵Frobenius误差＋偏移L2误差/0.4；不可用或无效估计固定记10.5。条件误差只描述有效估计，不能代替全人口比较。", "",
            f"![辨识与完整成本](../{figure_paths[1].relative_to(ROOT).as_posix()})","",
            "|任务|条件|完整窗口/全部|候选有效/完整|候选有效/全部|","|---|---|---:|---:|---:|"]
        for r in summary["strata"]:text.append(f"|{TASKS[r['task']]}|{'不变' if r['condition']=='UNCHANGED' else '变化'}|{r['complete']}/{r['attempts']}|{r['candidate_valid_complete']}/{r['complete']}|{r['candidate_valid_complete']}/{r['attempts']}|")
        text += ["","|候选减参考|平均差|95%组重采样区间|","|---|---:|---|"]
        for r in summary["contrasts"]:text.append(f"|位置＋历史 − {LABELS[METHODS.index(r['reference'])]}|{number(r['mean_difference'])}|[{number(r['ci95'][0])}, {number(r['ci95'][1])}]|")
        text += ["","两个主要比较的区间上界都须小于0，每个任务/条件完整率须≥0.5，完整窗口中的候选有效率须≥0.9。", "",
            "冻结门槛结果：`"+json.dumps(summary["gates"],ensure_ascii=False)+"`。", "",
            f"计划边界不可用共{summary['planned_boundary_unavailable']}例；采集期间提前任务成功{summary['early_task_successes']}例。两者是不同统计，不能把计划测量不可用写成任务失败。", "",
            "区间以这一次冻结名义模型为条件，不包含重新训练的波动；也不是物理预测置信区间。"]
    text += ["","## 全部未完成与无效案例","","|阶段|采集停止原因|案例数|","|---|---|---:|"]
    for stage,audit in (("名义训练",train),("独立辨识",packet["qualify"])):
        if audit is not None:
            for reason,count in sorted(Counter(r["collection_stop_reason"] for r in audit["rows"]).items()):text.append(f"|{stage}|{reason}|{count}|")
    if summary is not None:
        text += ["","|方法|估计状态/原因|案例数|","|---|---|---:|"]
        for r in summary["methods"]:
            for reason,count in r["reasons"].items():text.append(f"|{LABELS[METHODS.index(r['method'])]}|{reason}|{count}|")
    case_folder=figure_paths[0].parent.relative_to(ROOT).as_posix()
    text += ["",f"逐案例记录包括提前成功、无完整窗口和无效估计，见[全部案例](../{case_folder}/all_cases.json)与[不可用或无效案例](../{case_folder}/unavailable_or_invalid_cases.json)。没有使用其他方法代执行来补齐结果。", "",
        "## 完整成本","","|实际采集阶段|控制步|受控重置|全部重置|仿真帧|采集墙钟（秒）|","|---|---:|---:|---:|---:|---:|"]
    for stage,audit in (("新名义训练",train),("独立辨识",packet["qualify"])):
        if audit is not None:
            cost=audit["costs"];ledger=cost["lifecycle"]
            text.append(f"|{stage}|{cost['total_steps']}|{ledger['by_phase']['CONTROLLED_RESET']['reset_completed']}|{ledger['counts']['reset_completed']}|{ledger['counts']['simulation_frames_completed']}|{cost['collection_wall_ns']/1e9:.3f}|")
    old=manifest["config"]["historical_nominal_cost"]
    text += [f"|历史名义来源|{old['environment_steps']}|{old['controlled_resets']}|{old['all_reset_calls']}|{old['simulation_frames']}|—|","",
        f"本轮模型拟合共{len(bank['fits'])}次尝试，拟合阶段墙钟{(bank['fit_completed_ns']-bank['started_ns'])/1e9:.3f}秒。历史来源单独收费；新实际采集只发生一次。"]
    if summary is not None:
        text += ["","|方法|在线控制步|新名义步|历史步|每配对单元总步数|全部重置|仿真帧|在线优化函数评估|","|---|---:|---:|---:|---:|---:|---:|---:|"]
        for r in summary["costs"]["method_accounting"]:text.append(f"|{LABELS[METHODS.index(r['method'])]}|{r['online_steps']}|{r['new_nominal_steps']}|{r['historical_steps']}|{r['steps_per_paired_unit']:.3f}|{r['all_reset_calls']}|{r['simulation_frames']}|{r['online_optimizer_nfev']}|")
        text += ["","每个新模型计入完整新名义训练；C8与积分参考在其实际证据结束处计费，不承担新模型训练和后续脉冲成本。以上方法账共享同一物理采集，不能求和当作实际总费用。", "",
            f"独立评价复算另使用{packet['numeric_audit']['independent_optimizer_nfev']}次优化函数评估，审计墙钟{packet['numeric_audit']['wall_ns']/1e9:.3f}秒。审计没有新增机器人步骤或API调用。"]
    text += ["","## 结论边界","",
        "当前结果只涉及指定测量操作与参数辨识。完整运动历史基线、支付探测成本后的真实任务续跑、自适应获取决策和独立时序任务评价仍需完成。积分参考不能代表所有历史辨识方法。", "",
        "这轮没有新增LLM API调用、自然记忆或策略权重训练。上述组件结果不能直接作为算法创新、任务收益或完整CCF A投稿就绪的证据。"]
    return "\n".join(text)+"\n"


def main(path):
    packet,bindings=load_closed(path)
    require(not REPORT.exists() and not OUT.exists(),"report already produced")
    OUT.mkdir(parents=True)
    images,font=figures(packet,OUT)
    train=[{"stage":"TRAIN",**r} for r in packet["train"]["rows"]]
    qualify=[{"stage":"QUALIFY",**r} for r in packet["estimates"]]
    write(OUT/"all_cases.json",train+qualify)
    write(OUT/"unavailable_or_invalid_cases.json",[r for r in train+qualify if not r["complete_window"] or any(not f["valid"] for f in r.get("fits",{}).values())])
    with REPORT.open("x",encoding="utf-8",newline="\n") as handle:handle.write(markdown(packet,images))
    for p,value in bindings.items():require(sha(p)==value,"source changed while rendering")
    outputs=[*images,OUT/"all_cases.json",OUT/"unavailable_or_invalid_cases.json",REPORT]
    write(OUT/"report_receipt.json",{**{k:packet["manifest"][k] for k in IDENTITY},
        "inputs":{p.relative_to(ROOT).as_posix():v for p,v in bindings.items()},
        "outputs":{p.relative_to(ROOT).as_posix():sha(p) for p in outputs},"source_sha256":sha(Path(__file__)),
        "font":font,"python_version":sys.version,"new_environment_steps":0,"new_api_calls":0,"new_model_fits":0,
        "scope":"Read-only rendering of closed audited records; figure/manual visual review remains required"})
    print(json.dumps({"report":str(REPORT),"figures":[str(p) for p in images]},ensure_ascii=False))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest",required=True,type=Path)
    main(parser.parse_args().manifest)
