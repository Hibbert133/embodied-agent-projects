# 本地交付与复算

科学实现先在 `636d6b1` 冻结；研究执行目录为
`outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39/`。
本目录的归档、图形和交付核对只读取已经完成的记录，不收集数据、不训练模型、不调用 API。
主要中文报告位于 `reports/response_model_qualification_v1_zh.md`。

## 原件、分片与恢复

原始 gzip 文件与实际恢复副本留在本地。Git 保存无损二进制分片及索引，
`transport_v1/index.json` 将原件路径、原件哈希、每套分片索引及恢复验证逐条关联。
`artifact_provenance.json` 为所有结果绑定实验编号、manifest 与冻结提交。
原始记录没有因为归档或增加来源元数据而重写。

在缺少原始大文件的新检出中，从仓库根目录执行下面的 Python 逻辑即可恢复；
已有文件只核对哈希，绝不覆盖：

```python
from pathlib import Path
import json
from scripts.archive_action_response import restore, sha

root = Path("outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39")
index = json.loads((root / "transport_v1/index.json").read_text(encoding="utf-8"))
for item in index["artifacts"]:
    target = root / item["source"]
    if not target.exists():
        restore(root / item["index"], target)
    assert sha(target) == item["source_sha256"]
```

审计入口为 `scripts/audit_response_model_qualification_v1.py`，模式
TRAIN／CAL／QUAL／models／calibration／numeric。原输出不可覆盖；完整复算应先
复制整个执行目录到新位置，保留所有已审计输入，再将对应审计旧输出保存在复制目录之外，
向入口传入复制目录的 manifest。该入口不会创建、重置或推进环境。
绝不重新调用收集入口或复用研究种子。

## 费用解释

科学采集、C4/C8 参数拟合、六个 TRAIN 响应模型、独立数值重建、软件夹具各自计费。
记录审计的 `independent_cold_fit_recomputations` 与 nfev 是额外计算复算；
两次响应模型数值审计各重建六组系数，是审计计算，没有生成新的研究候选或重新挑选模型。
经验分位数、资格预测与 bootstrap 只做计算，不增加机器人交互。
冻结验证的 `unittest_native_costs.json` 只覆盖该次全仓库调用中具有仪器回执的夹具；
先前控制台定向测试和无仪器旧测试不在该回执之中，不能将未覆盖费用填为零。

预测资格、参数数值合法性和含获取成本的任务收益分别判断。所有负结果、缺失与提前
结束保留；预测资格即使通过，也不能替代独立任务比较、算法新颖性或 CCF A 论文目标。
