# Held-Out Active-Evidence Agent Pilot

## Question

When passive rollout symptoms are deliberately matched across stable bias and
stochastic noise, does repeated diagnostic evidence improve mechanism diagnosis,
and can a tuning-frozen uncertainty gate acquire that evidence selectively?

This experiment evaluates evidence acquisition rather than Push success. It uses a
fixed low-level policy and does not call an online model.

## Data and leakage boundary

Seeds 310–319 were rerun for all five registered fault conditions without video,
probe, or corrective intervention. The resulting 50 initial rollouts reproduced
the existing validation baseline on success, steps, and final distance for all
50/50 condition–seed rows. The rerun added the previously missing return and
progress fields.

The held-out builder retained 28 stable-bias failures and two stochastic-noise
failures. Using the tuning-frozen matching rule, it formed two pairs (four cases).
Mean standardized passive distance was 0.1211. Pair construction used only return,
final distance, and progress; mechanism labels and perturbation parameters remained
Oracle audit fields.

## Compared agents

- **Passive:** tuning-fitted standardized nearest-class-centroid model over the
  three passive features; no additional environment interaction.
- **Always-probe:** always uses the existing four-repeat symmetric probe and its
  tuning-frozen consistency threshold.
- **Seeded random-probe:** independent deterministic request decision with seed
  20260730 and probability 0.375, equal to the tuning gate's request rate.
- **Uncertainty-gated:** requests a probe when passive centroid-margin uncertainty
  reaches the tuning-selected threshold 0.84458. The threshold was not changed on
  held-out cases.

## Real held-out result

| Method | Correct | Balanced accuracy | Probe requests | Probe steps |
|---|---:|---:|---:|---:|
| Passive | 2/4 | 50% | 0/4 | 0 |
| Always-probe | 4/4 | 100% | 4/4 | 256 |
| Seeded random-probe | 3/4 | 75% | 2/4 | 128 |
| Uncertainty-gated | 2/4 | 50% | 0/4 | 0 |

Always-probe corrected both passive noise errors, providing two additional correct
diagnoses at a cost of 256 environment steps, or 0.78125 additional correct cases
per 100 probe steps. The one seeded random control happened to probe one of the two
noise cases and obtained one additional correct diagnosis.

The uncertainty gate requested no probes. Held-out uncertainties ranged from
0.7126 to 0.8342, all below the frozen threshold. It therefore reproduced the
passive 2/4 result. This is a useful negative result: the repeated probe contains
diagnostic evidence, but the current passive distance margin does not reliably
predict when that evidence is needed.

The comparison figure is generated directly from the real summary CSV:
`outputs/ambiguity_benchmark/figures/heldout_method_comparison.png`.

## Interpretation and limitations

The result supports only a narrow claim: on four matched held-out synthetic cases,
repeated evidence separated stable from stochastic execution where the registered
passive baseline labeled both noise failures as stable bias. It does not show that
the selective Agent works; the frozen gate failed to request evidence.

Important limitations:

- only two held-out noise failures were available, producing four matched cases;
- deterministic bias has zero repeat variance and noise std is 0.60;
- the passive centroid baseline uses only three terminal aggregate features;
- the random result is one seeded control, not an expectation over random seeds;
- diagnosis was not yet connected to a fresh corrective-intervention verification
  comparison in this benchmark.

MetaWorld/Gymnasium emitted the existing warnings about equal observation-space
bounds, reset/step observations outside the declared space, and scripted policy
commands being clipped. They did not invalidate this run: all 50 newly collected
execution outcomes matched the prior validation artifact on success, steps, and
final distance.

## Reproduction

```powershell
python scripts/collect_ambiguity_rollouts.py
python scripts/build_bias_noise_ambiguity_benchmark.py --oracle-audit outputs/ambiguity_benchmark/heldout_rollouts/oracle_audit.jsonl --probe-results outputs/autoresearch/probe_consistency_validation/results.csv --threshold-selection outputs/autoresearch/probe_consistency_tuning/threshold_selection.json --output-dir outputs/ambiguity_benchmark/bias_noise_heldout_v1 --benchmark-id bias_noise_heldout_v1 --split heldout
python scripts/evaluate_ambiguity_agents.py
python scripts/plot_ambiguity_agent_comparison.py
```

## Next decision

Do not tune another threshold on these four cases. The next experiment should
increase the number of matched held-out stochastic failures and test a causal
evidence-need signal derived from within-rollout temporal inconsistency. The signal
must be selected on new development seeds and then frozen before another held-out
comparison.
