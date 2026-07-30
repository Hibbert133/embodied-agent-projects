# Online Candidate-Utility Agent Protocol

## Research question

The stochastic-retry study rejected a direct mapping from diagnosed fault type to
recovery skill. This protocol asks a narrower robotic-agent question: can an
online high-level model use short, action-conditioned evidence to choose between
two executable recovery candidates better than a fixed routing rule?

This is candidate-specific utility reasoning, not fault-label prediction. The
online model does not generate low-level actions or arbitrary controller gains.

## Agent boundary

The trusted simulator constructs two typed candidates from Agent-visible evidence:

1. `bias_compensation`: the bounded correction and schedule inferred by the frozen
   `research_r1_c1` recovery policy;
2. `stochastic_retry`: no correction, with a fresh execution-noise realization.

Each candidate receives an independent 80-step probe. The online Agent sees the
initial failure summary, structured active-probe diagnosis, candidate contracts,
and candidate-probe outcomes. It selects exactly one candidate for the only full
recovery rollout and returns a hypothesis, measurable expected effect,
verification condition, and confidence.

Injected perturbation type, parameters, executed actions, clipping fields, Oracle
labels, and perturbation seeds are rejected by the payload validator. The final
rollout uses a third independent perturbation stream, so the candidate probe does
not reveal the future execution realization.

## Frozen development protocol

- task: MetaWorld `push-v3`;
- cases: the six tuning cases in
  `outputs/autoresearch/search_tuning/selected_case_ids.json`;
- recovery config: `research_r1_c1`;
- candidate probe budget: 80 steps per candidate;
- final recovery budget: one rollout, at most 500 steps;
- online budget: at most six API calls, one per case;
- selection priority: recovery success first, total environment interactions
  second.

This is a development experiment. It must not be reported as held-out evidence.
The script checkpoints every completed case and resumes only when its recorded run
configuration is unchanged.

The simulator-only preparation can be run without a credential. It writes the
exact leakage-checked candidate evidence that the later online call will reuse:

```powershell
.\scripts\run_online_utility_agent.ps1 -Model glm-5.1 -RunName glm51_utility_dev -PrepareOnly
```

## Secure execution

```powershell
.\scripts\run_online_utility_agent.ps1 `
    -Model glm-5.1 `
    -BaseUrl https://api.modelarts-maas.com/anthropic `
    -RunName glm51_utility_dev `
    -ApiTimeout 300
```

The wrapper requests the key through hidden local input and removes it from the
process environment afterward. Never store or paste the key into repository
files, shell history, experiment artifacts, or chat.

## Outputs and interpretation boundary

Each run writes `run_config.json`, leakage-safe `prepared_cases.jsonl`, per-case
`results.csv`, `planner_audit.jsonl`, and `summary.csv` under
`outputs/online_utility_agent/<run-name>/`. Model identity, prompt version/hash,
token usage, latency, selected candidate, environment-step cost, and final outcome
are auditable.

Mock unit tests establish schema enforcement, exact candidate selection, and
leakage rejection only. A real success-rate statement requires completing the
secure online command. Six tuning cases are integration evidence, not a
statistical or general robotic-agent claim.
