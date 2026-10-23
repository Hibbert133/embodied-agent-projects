# 坐标框架歧义独立审计

状态 `COMPLETED_PREREQUISITE_PASS`；完整性 `PASSED`。

结构见证：8/8；上下文盲/知上下文评估上界：8/16（分母 16）。

| 方法 | 成功/16 | FRAME0/8 | FRAME90/8 | 平均在线步 | 平均含离线摊销步 | 正确旋转/16 |
|---|---:|---:|---:|---:|---:|---:|
| FIXED_A_PREFIX4 | 8 | 8 | 0 | 283.62 | 283.62 | None |
| FIXED_B_PREFIX4 | 8 | 0 | 8 | 284.50 | 284.50 | None |
| UNCORRECTED_PREFIX4 | 8 | 8 | 0 | 283.31 | 283.31 | None |
| MODEL_REPEAT8 | 8 | 8 | 0 | 285.38 | 429.38 | 8 |
| MODEL_REVERSE8 | 16 | 8 | 8 | 72.12 | 216.12 | 16 |
| MODEL_SYM16 | 16 | 8 | 8 | 80.25 | 224.25 | 16 |
| LEGACY_AFFINE16 | 8 | 8 | 0 | 288.88 | 432.88 | None |
| LEGACY_NEAREST16 | 4 | 4 | 0 | 399.81 | 543.81 | None |
| FIXED_A_REVERSE8 | 8 | 8 | 0 | 285.12 | 285.12 | None |
| FIXED_B_REVERSE8 | 8 | 0 | 8 | 287.00 | 287.00 | None |
| NO_PROBE | 8 | 8 | 0 | 282.38 | 282.38 | None |

结构门 `{'common_prefix_all': True, 'repeated_probe_all': True, 'reverse_separates_all': True, 'disjoint_actions': True, 'correct_fixed_controller': True}`。
标准基线门 `{'identification': True, 'task_count': True, 'choice_gain': True, 'legacy_affine': True, 'legacy_nearest': True, 'no_probe': True, 'cheap_vs_full': True}`。

物理收集 45318 步/176 次初始重置；已有离线资源 2,304 步/144 次重置；API 0 次。

所有先验访问方法均按 16 单元加 144 步/9 次重置；旧资格不认证新的 ARX/旋转模型。

Training-only reconstruction, visible decision replay, complete observation/RNG chains, fixed-policy commands and evaluator frame/noise/clipping inputs. Task dynamics are not resimulated.

构造例中的标准基线结果不是新算法、真实故障频率或 CCF A 发表证据。
