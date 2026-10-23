# 只读审计时间单位修复 v2

冻结原审计器 `analyze_acquisition_value.py` 对模拟时钟推进硬编码 0.01 秒，
假设单帧为 MuJoCo 默认 0.002 秒、每 Env.step 五帧。完整采集后的第一次
审计因此在首个冷源失败，原失败日志保留，不宣称原审计器通过。

清单已绑定的 MetaWorld 场景 XML 实际设置 timestep=0.0025 秒。采集执行器
原本逐步比较模型实际 `opt.timestep * frame_skip`，每次五帧为 0.0125 秒。
帧预算、步预算、控制与探测行为都不因这个审计错误改变；完整数据不重跑。

新文件 `scripts/audit_acquisition_value_clock_v2.py` 保留原核查，仅将硬编码
时钟差改为三个已绑定任务 XML 编译出的模型时间步。编译只创建 MjModel，
不创建 MjData、环境、重置或调用 mj_step。包／资产、原六百二十个源文件
及冻结 Git 字节仍由原清单核对。每步五帧另由完整账本独立核对。

新版本保存编译出的时间单位与 XML 散列、修复源提交和原审计未通过标记。
这属于读取原数据的审计修正，不是算法或协议行为变更。成功仍须完整重放
全部轨迹、费用、实际选择和配对；错误修正本身不证明剩余检查通过。

[MuJoCo 状态与模拟文档](https://mujoco.readthedocs.io/en/3.3.0/programming/simulation.html)
仅用于 API 使用范围，实际时间单位以清单绑定资产的编译结果为准。
