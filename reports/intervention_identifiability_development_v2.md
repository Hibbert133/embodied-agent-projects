# Intervention Identifiability Development v2

## Question

Does a broad execution-mechanism class reliably identify which bounded
corrective intervention has higher per-instance utility?

This development audit follows the frozen P1 negative result. It does not tune
or overwrite held-out seeds 330--339 and does not implement a new online
selector.

## Setup and provenance

- Run: `development_20260731T030710Z_a1756e42d473`
- Source commit: `a1756e42d47327e79b47b8e6e73d6d57d2fe2959`
- Seeds: 400--409
- Conditions: four stable-bias conditions and one stochastic-noise condition
- Full population: 50 initial rollout units
- Operational population: 32 failed initial rollouts
- Registered probe: one 64-step repeated symmetric XY probe
- Candidates: probe-grounded compensation and independent stochastic retry
- Verification: matched task reset and perturbation realization
- Rendering/API calls: disabled / 0

## Results

The paired comparable population contains 31/32 operational units (96.9%). One
compensation candidate returned `ABSTAIN`; this is reported as unavailable and
is not coerced into an action.

| Quantity | Result |
| --- | ---: |
| Compensation preferred | 28/31 |
| Retry preferred | 3/31 |
| Evaluator mechanism aligned with preferred candidate | 30/31 (96.8%) |
| Passive belief aligned | 27/31 (87.1%) |
| Post-probe belief aligned | 30/31 (96.8%) |
| Belief changes | 5 |
| Changed selections with better outcome | 4 |
| Changed selections with worse outcome | 1 |

Stable-bias cases were internally consistent: all 27 comparable failures
preferred compensation. Stochastic-noise cases were heterogeneous: retry was
preferred in 3/4, while compensation was preferred in 1/4. Compensation
recovered 27/31 executable cases (87.1%); retry recovered 3/32 (9.4%). These
candidate rates use different denominators because one compensation candidate
was unavailable.

## Counterexample

For `development_case_0042` (`fault_05`, seed 401), the probe changed the belief
from stable bias to stochastic noise and therefore changed the candidate from
compensation to retry. Compensation was `INCONCLUSIVE` at 500 steps, while retry
was `REJECTED` at 500 steps. The probe improved the mechanism label but selected
a worse verification status.

Conversely, cases 0048 and 0049 changed from compensation to retry and recovered
successfully in 74 and 77 verification steps. Thus the stochastic-noise class
contains both useful and harmful retry decisions under the current candidate
set.

## Interpretation

Mechanism belief is a strong intervention prior, especially for stable bias,
but it is not a sufficient per-instance utility estimate. This explains why P0
diagnostic improvement did not automatically transfer to P1 recovery benefit.
The next method should target the residual ambiguity inside the noise stratum,
not retune the frozen evidence-allocation threshold.

This is development evidence only. It does not establish held-out improvement,
does not justify Verified Episodic Memory, and does not support an online-policy
learning claim.

## Reproduction

```powershell
python scripts/run_intervention_identifiability_development.py
python scripts/validate_intervention_identifiability_artifacts.py --run-dir outputs/intervention_identifiability/runs/development_20260731T030710Z_a1756e42d473
python scripts/plot_intervention_identifiability.py --run-dir outputs/intervention_identifiability/runs/development_20260731T030710Z_a1756e42d473
```
