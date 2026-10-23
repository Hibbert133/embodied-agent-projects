# GLM Interface Ablation v1

Gate A uses fresh seeds 4000--4099 and collects the first 15 eligible failures
from each of persistent stable bias and persistent stochastic noise. Eligibility
and Agent evidence are persisted before paired candidate outcomes.

The exact same 30 cases are sent through full, compact, and compact-plus-skill-
semantics interfaces. The model predicts both skills and selects compensation,
retry, or abstention. No decision controls MuJoCo. Condition identity is used
only for evaluator stratification.

Ninety base calls are mandatory. Invalid outputs receive at most one repair
after all base calls, with a hard total cap of 105. Exceeding the cap makes the
run incomplete. Promotion uses the frozen rates and comparative rule in
`configs/probemem_online/interface_ablation_v1.json`; results cannot retune the
payload, prompt, cases, or gate.
