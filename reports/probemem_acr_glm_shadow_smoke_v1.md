# GLM-5.2 Action-Reasoning Shadow Smoke v1

## Scope

Run `acr_glm_shadow_20260803T042234Z_cab016100670` used commit
`cab01610067029708d0d00cb9ca467fa78cc3e00`. Three fixed development rows were
sent through an allowlisted Agent-visible payload. Paired evaluator outcomes
were removed before request construction. Model decisions were logged but never
executed.

## Operational result

| Metric | Result |
|---|---:|
| Valid structured cases | 3/3 |
| API calls | 3 |
| Schema repairs | 0 |
| Fail-closed cases | 0 |
| Median latency | 22.59 s |
| Latency range | 21.29–25.42 s |
| Input tokens | 1,271 |
| Output tokens | 2,290 |
| Environment steps | 0 |
| Executed model actions | 0 |

All three shadow decisions selected `SWITCH_TO_BOUNDED_COMPENSATION`. This is a
successful tool-contract and leakage-boundary smoke, not evidence of useful
action discrimination. With only three qualitative calls, no recovery,
accuracy, calibration, or superiority claim is permitted.

## Research interpretation

The engineering path to GLM is now ready: the provider credential is loaded
from the ignored DPAPI-encrypted local file, requests use a strict action-
conditional schema, invalid output fails closed, and the host owns all robot
execution. The scientific blocker remains evidence identifiability, not API
integration.

The fastest defensible next step is a development benchmark with an
episode-persistent latent execution context. That benchmark should first show
that Agent-visible evidence distinguishes action utility. The same frozen shadow
contract can then become a registered GLM ablation without redesigning the API
layer.
