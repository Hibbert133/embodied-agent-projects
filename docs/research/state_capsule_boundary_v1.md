# 恢复状态的用途与已有能力边界

当前条件续接分析没有完整隐藏状态资格；不能在旧记录上补造未实际执行的分支。
后继若要从同一决策状态比较复用、重测或其他程序，需要先验证评价者状态恢复。
这是采集工具的必要组件，本身不是新选择算法或任务收益证据。

[MuJoCo 3.3官方C接口](https://mujoco.readthedocs.io/en/3.3.0/APIreference/APIfunctions.html)
已有完整模型／数据复制和状态向量接口；[官方仿真说明](https://mujoco.readthedocs.io/en/3.3.0/programming/simulation.html)
说明模拟状态与控制／外部状态的关系。因此复制状态或从同一状态分叉不构成创新。
[官方Python说明](https://mujoco.readthedocs.io/en/3.3.0/python.html)提醒数组直接引用原生内存。
本机Python没有直接导出mj_copyModel/mj_copyData，但类有原生地址和复制支持；
本实现严格绑定安装库的3.3.0 ABI后调用已有C接口，不修改库。

本机MetaWorld的环境__getstate__/__setstate__还会重新初始化MujocoEnv并设置
qpos/qvel，不能直接用作精确续接。`init_left_pad`等任务字段是原生数据视图，
因此只保存数值而破坏共享关系也可能改变后续行为。实现保留原生对象地址，
序列化白名单Python图，并保留原生视图、普通数组视图及共享RNG关系。

Gym RecordEpisodeStatistics在结束时使用真实perf_counter；这个时间不能回退。
轨迹比较只排除info.episode.t，原始时间与费用照存。政策只读观测和固定任务身份，
不会读统计耗时。若后继政策使用墙钟，本资格不能直接外推。

资格人口和容差在[独立协议](../protocols/state_capsule_qualification_v1.md)预先冻结。
胶囊仅供评价者，同进程、不从外部文件加载。未知对象、回调或活动渲染均拒绝。
注册恢复合同通过仍不是普遍隐藏状态证明、真实硬件证据或条件价值估计。
后继必须另外说明分支行为支持、多未来误差、选择机制和新颖性；不再根据旧批次
调阈值，也不把评价者反事实标签当自然在线记忆。
