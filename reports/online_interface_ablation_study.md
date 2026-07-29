# Online Agent Interface Ablation

## Question

Does skill grounding, rather than model version alone, explain the improvement
from the failed raw-probe online Agent to reliable planar recovery?

## Frozen 2x2 design

The experiment crosses GLM-5.1/GLM-5.2 with raw-probe/skill-grounded interfaces.
All cells use MetaWorld push-v3, seeds 250-254, injected audit bias
`(x=+0.14,y=-0.14)`, four 8-step probes, one API call, and one recovery rollout
per initial failure. The split is a development set, not held-out evaluation.

The raw interface asks the model to infer and quantize correction values. The
skills interface supplies two executable contracts derived only from visible
probe evidence; the model selects a skill and schedule but cannot modify its
correction.

## Real results

| Model | Interface | Recovered | Mean recovery steps | Final distance | Mean API latency |
|---|---|---:|---:|---:|---:|
| GLM-5.1 | raw | 2/5 | 355.2 | 0.17973 | 58.39 s |
| GLM-5.1 | skills | 5/5 | 92.0 | 0.04798 | 30.84 s |
| GLM-5.2 | raw | 2/5 | 355.0 | 0.13658 | 93.07 s |
| GLM-5.2 | skills | 5/5 | 92.0 | 0.04808 | 33.26 s |

Both raw cells selected `dominant_only` in all five cases and recovered the same
two seeds. Both skills cells selected `simultaneous_xy_repair` in all five cases
and recovered every seed. GLM-5.1 selected `phase_aware` for seed 250 while the
other skill decisions used `whole`; its 64 recovery rollout steps match the
existing whole-schedule result for that seed, so this does not establish a
schedule-selection benefit.

## Interpretation

On this fixed development condition, the descriptive interface effect is large
and replicated across model versions: skill grounding changes recovery from 40%
to 100% and reduces mean recovery interaction from roughly 355 to 92 steps.
Changing GLM-5.1 to GLM-5.2 does not change recovery success within either
interface. This supports the claim that the interface—not a model upgrade—is the
main mechanism in this pilot.

The skills Agent does not outperform the deterministic simultaneous controller;
it selects that controller. Its current value is bounded orchestration,
interpretable hypotheses, and explicit verification conditions. All episodes
share nearly identical probe estimates and the same optimal skill, so the study
does not yet demonstrate adaptive skill selection. A heterogeneous benchmark
must contain cases where dominant-only, simultaneous, schedule gating, and stop
are each optimal under fixed budgets.

## Warnings and limitations

MetaWorld/Gymnasium observation-space and policy clipping warnings appeared in
all cells and did not cause missing episodes. Online CSV currently omits clipping
fractions, so clipping remains an Oracle-audit limitation. Results are n=5 per
cell on development seeds and should not be presented with inferential or
generalization claims.

## Reproduction

```powershell
.\scripts\run_online_interface_ablation.ps1 -BaseUrl https://api.modelarts-maas.com/anthropic -ApiTimeout 300
python scripts/summarize_online_interface_ablation.py --input-root outputs/online_planar_agent --output-csv outputs/online_planar_agent/interface_ablation_summary.csv
python scripts/plot_online_interface_ablation.py --summary-csv outputs/online_planar_agent/interface_ablation_summary.csv --output outputs/online_planar_agent/figures/model_interface_2x2.png
```
