# Online Candidate-Utility Agent: Development Result

## Hypothesis

The prior stochastic-retry experiment showed that fault classification alone does
not determine recovery value. We therefore tested whether an online GLM-5.1 Agent
could select between bounded bias compensation and an independent stochastic retry
using candidate-specific 80-step probe outcomes.

## Setup

- MetaWorld `push-v3`, six frozen tuning failures;
- frozen `research_r1_c1` active diagnosis and recovery configuration;
- one 80-step probe for each typed candidate;
- one full recovery rollout, maximum 500 steps;
- independent reproducible perturbation streams for both probes and final execution;
- six API calls using prompt `candidate-utility-agent-v1`;
- Agent payload validated against Oracle and injected-fault fields.

This is a development set result, not held-out evidence.

## Real result

| Method | Recovered | Recovery rate | Mean environment steps | Mean final distance |
|---|---:|---:|---:|---:|
| Always compensation | 6/6 | 100.0% | 149.50 | 0.04896 |
| Always retry | 0/6 | 0.0% | 500.00 | 0.32181 |
| Probe-greedy rule | 5/6 | 83.3% | 316.00 | 0.08459 |
| Online GLM-5.1 Agent | 5/6 | 83.3% | 316.00 | 0.08459 |
| Post-hoc candidate Oracle | 6/6 | 100.0% | 304.50 | 0.04896 |

The online Agent agreed with the probe-greedy rule on all 6 cases. It used 4,614
input tokens and 3,636 output tokens (8,250 total), with 131.28 seconds aggregate
API latency and 21.88 seconds mean latency per decision.

## Failure analysis

For `case_0041`, neither candidate succeeded within the 80-step probe. Retry moved
the object closer to the goal (0.1172 versus 0.2927), so both GLM-5.1 and the
probe-greedy control selected retry. The full retry failed after 500 steps at
distance 0.2630.

The matched counterfactual compensation rollout used the same final perturbation
stream and succeeded at step 431 with distance 0.0492. The short compensation probe
therefore produced a false-negative utility signal: slow eventual recovery looked
worse than fast early progress. This is a horizon mismatch, not evidence that the
model inferred the injected fault incorrectly.

## Interpretation

The experiment validates the online integration, leakage boundary, strict candidate
contract, resumable API audit, and reproducible counterfactual evaluator. It does
not show a performance benefit from the online model. On this development set the
online Agent exactly imitates a simple deterministic heuristic, costs six API calls,
and underperforms the cheaper fixed compensation policy.

The scientifically relevant result is a concrete robotic-Agent failure mode:
candidate ranking from fixed short probes is biased toward immediate progress and
can miss delayed recovery. A stronger Agent interface needs horizon-aware evidence
or uncertainty over probe-to-rollout extrapolation, rather than a longer prompt.

## Artifacts

- `outputs/online_utility_agent/glm51_utility_dev/results.csv`
- `outputs/online_utility_agent/glm51_utility_dev/planner_audit.jsonl`
- `outputs/online_utility_agent/glm51_utility_dev/control_results.csv`
- `outputs/online_utility_agent/glm51_utility_dev/control_summary.csv`
- `outputs/online_utility_agent/glm51_utility_dev/utility_control_comparison.png`

## Reproduction

```powershell
.\scripts\run_online_utility_agent.ps1 -Model glm-5.1 -BaseUrl https://api.modelarts-maas.com/anthropic -RunName glm51_utility_dev -ApiTimeout 300

python scripts/evaluate_online_utility_controls.py --run-dir outputs/online_utility_agent/glm51_utility_dev

python scripts/plot_online_utility_controls.py --summary-csv outputs/online_utility_agent/glm51_utility_dev/control_summary.csv --output outputs/online_utility_agent/glm51_utility_dev/utility_control_comparison.png
```
