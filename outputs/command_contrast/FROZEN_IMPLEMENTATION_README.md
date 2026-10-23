# 实际命令差分资格：冻结实现交付

本目录保存新收集器、审计器和统计入口的零交互软件验证。科学配置与人口位于 `configs/movement_task/command_contrast_qualification_v1.json`，中文协议位于 `docs/protocols/command_contrast_qualification_v1_zh.md`。

实现冻结不等于已经采集。纯数组／合成日志测试不构造、重置或推进环境。原生软件契约 15 执行、科学资格 540 执行均须在冻结提交之后逐阶段通过；最终是否运行，以 preparation 及原始日志为准。空间不足时只保存准备失败回执，不登记已执行种子，不创建科学 manifest，不训练模型。

验证回执在 `validation_v1`。早期软件断言失败及其源码片段保留，修复不改写旧实验数据；正式通过回执另列。旧 1,558 项测试只有在全部 900 个绑定 Python 源码和原始回执哈希一致时复用；新增纯数组测试、编译及依赖检查单独运行。Git 暂存字节和秘密扫描在 complete 回执中绑定。

执行顺序（项目 `.venv` Python，工作目录为仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -B scripts/run_command_contrast_qualification_v1.py prepare
.\.venv\Scripts\python.exe -B scripts/run_command_contrast_qualification_v1.py software-native --manifest <manifest绝对路径>
.\.venv\Scripts\python.exe -B scripts/audit_command_contrast_qualification_v1.py software-native --manifest <manifest绝对路径>
.\.venv\Scripts\python.exe -B scripts/run_command_contrast_qualification_v1.py qual --manifest <manifest绝对路径>
.\.venv\Scripts\python.exe -B scripts/audit_command_contrast_qualification_v1.py qual --manifest <manifest绝对路径>
.\.venv\Scripts\python.exe -B scripts/report_command_contrast_qualification_v1.py --manifest <manifest绝对路径>
```

prepare 退出码 2 表示 NEEDS_STORAGE，记录已经保存，不是采集成功。任何已开始原生阶段不可重试覆盖；首次目标不可用或软件契约不完整的原因也保留。通过软件测试不代表物理预测资格、完整任务收益或 CCF A 论文贡献。

此前受控训练已完成 162 次拟合和 720,000 次优化；全部神经模型未胜过强线性 F20。当前选择固定线性权重进行实际命令差验证，不再训练那版失败 GRU／ARX 或叠加选择规则。所有历史负结果、原始记录、分片和恢复副本不改写。当前及后续本协议在线 LLM API 调用为零，不推送、不合并。
