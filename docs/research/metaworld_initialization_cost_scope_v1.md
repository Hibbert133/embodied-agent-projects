# MetaWorld 初始化开销与原交互账本的范围

在本次单次收集尚未结束时，检查当前安装的 MetaWorld 3.1.1 源代码
发现：`gym.make("Meta-World/MT1", env_name=task, seed=seed)` 经 MT1
调用 `_make_tasks`，在一个临时环境中重置 50 次以生成任务向量，再
关闭该临时环境，创建供本次控制使用的环境。任务工厂没有缓存。
`LiveHost` 之后在控制环境执行一次已登记的初始重置。

原 `environment_resets` 是控制环境的登记计数，并非整个进程所有
临时模拟器的重置总数。原 `physical_steps` 是登记的 Env.step 调用。
库的 reset_hand 还包含内部 do_simulation；原轨迹没有单独记录这些
初始化物理帧，不能把 Env.step 计数写成全部 MuJoCo 工作量。

这里没有发现探测到任务之间的新重置：上述工厂活动发生在控制环境
轨迹开始之前，并使用另一个临时对象。连续衔接和原 500 个登记步骤
仍交给原审计检查。也不能从这一点宣布整个进程所有资源上限成立；
如果将原重置上限解释成所有库内部环境，原账本不能证明该上限。

补充工具用不创建 MuJoCo 环境的替身直接调用原 `_make_tasks`，核对
50 次临时 reset、一个临时对象、50 个向量及零 Env.step。它不读取
部分任务表现、不更改工厂或冻结协议，也不额外执行机器人任务。

在完整 4,608 案例的原审计通过后，按每案例一次工厂调用可**结构性
推算**临时任务生成重置 230,400 次；与控制重置相加为 235,008 次
reset 入口调用。原前向来源 288 实例在相同工厂下另有 14,400 次
推算临时重置，合计 14,688 次。推算须核对旧源工厂字节和版本。
这些不是当时记录的生命周期调用计数，也不等于实际机器人重置费。
它们需要与原登记计数分别展示，不能回改既有数据或注册门槛。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/audit_metaworld_setup_cost.py `
  --manifest outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481/manifest.json `
  --audit outputs/action_response/analysis_v1/audit.json `
  --output outputs/action_response/setup_cost_v1
```

输出绑定原主审计、源审计、当前安装源码和补充工具散列。历史源码
只保存包版本而未逐文件锁定，所以推算仍条件于当时具有同样初始化
语义；未知内部帧和额外底层操作不补作零费用。后续版本需要从工厂
创建前记录生命周期、初始化时间和模拟器物理工作量，并另行冻结。
