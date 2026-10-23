"""Static Chinese research figures from the completed immutable execution audit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def render(audit_path, output):
    a=json.loads(audit_path.read_text(encoding="utf-8"))
    if a.get("integrity")!="PASSED" or a.get("episodes")!=2304 or a.get("cold_sources")!=24:
        raise ValueError("complete execution audit required")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if not font.exists():raise FileNotFoundError("Chinese font required")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family":font_manager.FontProperties(fname=str(font)).get_name(),"axes.unicode_minus":False,
                         "font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    stats=a["statistics"];methods=list(stats["methods"]);rows=[stats["methods"][m] for m in methods]
    colors=["#176c9a" if m.startswith("MID") and not m.endswith("KEEP") else "#278269" if m.endswith("KEEP") else "#6d7782" for m in methods]
    fig,axes=plt.subplots(2,2,figsize=(16,12),gridspec_kw={"height_ratios":[1.35,1.]})
    y=np.arange(len(methods));successes=[r["successes"] for r in rows]
    ax=axes[0,0];ax.barh(y,successes,color=colors,height=.7)
    ax.set_yticks(y,methods);ax.invert_yaxis();ax.set_xlim(0,214);ax.set_xlabel("成功案例 / 192，包含停止与来源失败")
    ax.set_title("A  十二方法的完整任务结果",loc="left",fontweight="bold");ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True)
    for i,r in enumerate(rows):ax.text(r["successes"]+1.5,i,f"{r['successes']}  停止 {r['stops']}",va="center",fontsize=9)
    ax=axes[0,1];online=np.array([r["mean_steps"] for r in rows]);nominal=np.array([r["offline_nominal_steps"]/192 for r in rows]);cold=np.array([r["cold_source_steps"]/192 for r in rows])
    ax.barh(y,online,color=colors,height=.7,label="在线真实控制步")
    ax.barh(y,nominal,left=online,color="#c6d5e3",height=.7,label="完整名义来源摊销")
    ax.barh(y,cold,left=online+nominal,color="#e6b55e",height=.7,label="完整冷源摊销")
    ax.set_yticks(y,methods);ax.invert_yaxis();ax.set_xlabel("平均登记控制步（来源按 192 单元摊销）")
    ax.set_title("B  实际控制成本与来源",loc="left",fontweight="bold");ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True)
    limit=max(online+nominal+cold)*1.23;ax.set_xlim(0,max(100,limit))
    for i,r in enumerate(rows):ax.text(online[i]+nominal[i]+cold[i]+limit*.01,i,f"{r['mean_amortized_steps']:.1f}",va="center",fontsize=9)
    ax.legend(loc="upper center",bbox_to_anchor=(.5,-.14),ncol=3,fontsize=8,frameon=False)
    ax=axes[1,0];comparisons=stats["post_probe_update_contrasts"];names=list(comparisons);x=np.arange(len(names));width=.22
    fields=("mean_update_loss_difference","mean_probe_motion_loss_difference","mean_total_loss_difference")
    labels=("更新减 KEEP","KEEP 减继续旧控制","总差")
    for j,(field,label,color) in enumerate(zip(fields,labels,("#176c9a","#d79838","#278269"))):
        vals=[comparisons[m][field] for m in names]
        plotted=[float(v) if v is not None else 0. for v in vals]
        ax.bar(x+(j-1)*width,plotted,width,color=color,label=label)
        for i,value in enumerate(vals):
            if value is not None:ax.annotate(f"{value:.1f}",(x[i]+(j-1)*width,value),xytext=(0,5 if value>=0 else -12),textcoords="offset points",ha="center",fontsize=9)
    ax.axhline(0,color="#59616a",linewidth=.8);ax.set_xticks(x,[m+f"\nn={comparisons[m]['update_decisions']}" for m in names])
    ax.set_ylabel("平均截止损失差，负值表示改善")
    ax.set_title("C  同一探测后状态上的真实分支差",loc="left",fontweight="bold");ax.legend(fontsize=8,loc="upper center",bbox_to_anchor=(.5,-.19),ncol=3,frameon=False);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
    bounds=ax.get_ylim();span=max(1,bounds[1]-bounds[0]);ax.set_ylim(bounds[0]-.12*span,bounds[1]+.18*span)
    ax=axes[1,1];phases=a["lifecycle"]["by_phase"]
    order=[p for p in ("GOAL_GENERATION","CONTROLLED_RESET","CONTROL","FACTORY_SETUP") if p in phases]
    values=[phases[p].get("simulation_frames_completed",0)/1e6 for p in order]
    labels={"GOAL_GENERATION":"目标工厂临时环境","CONTROLLED_RESET":"控制环境初始安置","CONTROL":"在线控制与冷源探测","FACTORY_SETUP":"其他工厂初始化"}
    ax.barh(range(len(order)),values,color=["#6d7782" if p!="CONTROL" else "#176c9a" for p in order],height=.55)
    ax.set_yticks(range(len(order)),[labels[p] for p in order]);ax.invert_yaxis();ax.set_xlabel("实测 do_simulation 请求帧（百万）")
    ax.set_xlim(0,max(values)*1.24)
    for i,v in enumerate(values):ax.text(v+max(values)*.01,i,f"{v:.3f}",va="center",fontsize=10)
    ax.set_title("D  初始化与控制的模拟器工作量",loc="left",fontweight="bold");ax.grid(axis="x",alpha=.2);ax.set_axisbelow(True)
    gate=stats["repeat_gate"]
    fig.suptitle("同状态强探测、保留旧控制与任务收益",fontsize=19,fontweight="bold",y=.99)
    fig.text(.02,.014,f"8 流簇 / 48 名义上下文 / 4 噪声实现；主重复性门：{'通过' if gate['passed'] else '未通过'}。\n"
             "截止损失：成功取实际总步，失败／停止取 500。C 为真实分支差，不是纯信息价值；D 为模拟器入口帧，不是真实机器人费用。\n"
             "没有新的显著性、概率保证、效用预测器或算法创新声明。",fontsize=9,color="#414b56")
    fig.tight_layout(rect=(0,.075,1,.96),h_pad=3.,w_pad=4.)
    output.mkdir(parents=True,exist_ok=False)
    png=output/"figure.png";svg=output/"figure.svg"
    fig.savefig(png,dpi=220);fig.savefig(svg);plt.close(fig)
    result={**{k:a[k] for k in ("experiment_run_id","manifest_id","source_git_commit")},"primary_audit_sha256":sha(audit_path),
            "render_source_sha256":sha(Path(__file__)),"png_sha256":sha(png),"svg_sha256":sha(svg),
            "method_population":192,"stream_clusters":8,"new_robot_steps":0,"api_calls":0,"scope":"Static point estimates and matched recorded branch contrasts; no fitted model, resimulation or new inferential interval."}
    (output/"figure.json").write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    print(json.dumps(result))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError("new figure directory required")
    render(a.audit.resolve(),a.output.resolve())
