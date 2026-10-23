# 中文结果图

`render_figures.py` 仅绘制已保存的统计量，不重新抽样、不改变比较方向，也不
读取未完成实验的部分成绩。真实结果图要求中文报告及其来源回执已经生成，
并重新核对报告、统计审计、全部冻结输入的哈希。输出文件夹必须不存在。

三幅图分别展示全部四种方法的成功率与截止损失、预先指定的六组损失差及
95% 区间、实际在线步数与完整已知历史控制步摊销。六组比较中只有第一组
是主要比较，其余区间未作多重比较校正。失败时计 500 的截止损失不能当成
实际消耗步数，历史原生物理帧和工厂重置的未知部分也不计为零。

绘图使用独立环境，未向冻结的实验 `.venv` 安装任何包：

```powershell
$figurePython = 'C:\Users\Administrator\Documents\ChatGPT\robotic agent\.venv-movement-figures\Scripts\python.exe'
& $figurePython outputs/movement_task/reporting_v1/render_figures.py render outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf
```

此命令必须在完整收集、记录审计、统计、独立统计审计和中文报告全部完成后
执行。输出位于实验目录的 `figures/`，包括 PNG、可导出的矢量 SVG、中文
图集、精确绘图数值与来源哈希回执。`figure_environment.json` 记录解释器、
字体和依赖；`figure_requirements.lock` 绑定本机 Windows CPython 3.12 的
具体 wheel 哈希，不承诺直接适用于其他平台。SVG 将字形保存为路径。

`prepare_figure_fixture.py` 使用现有统计测试中的纯软件数据生成
`figure_fixture_v1.json`，没有读取本次真实任务结局或创建机器人环境。
`preview_figures_v1/` 是排版预览，所有图均带“软件样例 · 非实验结果”水印。
这些预览值不属于研究结果，不能放入论文作为实验数据。

重新绘制排版预览时，使用 `preview ... --output <新目录>`；默认文件和目录均拒绝覆盖。
对真实结果的检查仍须在数据完整后执行，排版预览不能替代科学审计。
