# Retry-Value Identifiability Audit v1

## Provenance and scope

This evaluator-only audit reads the immutable prospective continuous-feedback
run `acr_continuous_feedback_20260803T033027Z_fdff57ab321b` with manifest
`4bca2c97898ef8f36e3fc100cf5df19fe37808f9da44de5205b17a09d3d9e856`.
It adds zero environment interactions and zero API calls. The paired repeat
outcome is post-hoc evaluator information, not online Agent evidence.

The audit asks only whether preregistered first-verification scores rank the
value of one additional stochastic retry. It does not select a threshold or
make an online adaptation claim.

## Population

There were 30 second-decision cases. The evaluator-only paired retry was
`ACCEPTED` in 19 cases and non-accepted in 11, for a positive prevalence of
63.3%.

## Ranking results

| Preregistered score | ROC AUC | PR AUC / average precision |
|---|---:|---:|
| First observed progress | 0.464 | 0.633 |
| Negative first final object-goal distance | 0.488 | 0.678 |
| Categorical first status | 0.457 | 0.615 |

The positive prevalence itself is 0.633. Consequently, the apparent PR values
mostly reflect the high base rate and do not establish useful ranking. None of
the registered scores provides reliable ordering of second-retry acceptance.

## Cost–recovery frontier

`outputs/probemem_acr/retry_value_audit_v1/retry_cost_recovery_frontier.csv`
contains every observed score boundary plus never-retry and always-retry
endpoints. The figure is descriptive: it displays the cost paid and recoveries
obtained if an evaluator retrospectively thresholded each score. No operating
point is selected from this stream.

## Research interpretation

The first-retry verification outcome is valuable as a realized outcome, but its
registered status, progress, and distance summaries do not identify whether an
independent second retry will succeed. This separates two claims that had been
implicitly conflated:

1. executing another retry often helps (`19/30` paired candidates accepted);
2. deciding selectively which cases deserve that retry is not supported by the
   current feedback representation.

This closes the current scalar-feedback threshold line. The next experiment
must change the evidence source or the causal identification design; it must not
search another threshold on these 30 cases. GLM, Memory, validation, and held-
out execution remain unauthorized.
