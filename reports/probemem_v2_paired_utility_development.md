# ProbeMem Paired Intervention-Utility Development Result

Run: `probemem_paired_utility_20260731T172244Z_44bc5d206ddf`
Manifest: `92bfd43b97157a2dee3fb8da7c1e02fc0ac1dc3772fc53f50d3b12214335e501`
Source commit: `44bc5d206ddf31b59ec4256b614be30fdecdd1a2`

## Actual collection

- Full initial-rollout units: 20.
- Operational failed units: 10.
- Complete paired candidate units: 10.
- Compensation utility winners: 9.
- Retry utility winners: 1.
- Compensation accepted recoveries: 9/10.
- Retry accepted recoveries: 0/10.
- Operational stochastic-noise cases: 0.

## Interpretation

The only retry utility winner was episode 11, where both candidates were rejected. Retry won the preregistered failed-case tie-break because it preserved the initial object-goal distance, while compensation increased that distance. This is evidence of a harmful compensation edge case, not a successful retry recovery.

There is no episode in which retry recovered and compensation did not. Moreover, every registered noise rollout succeeded initially, leaving zero operational noise cases. The result is therefore `INSUFFICIENT_ACTION_UTILITY_DIVERSITY`: fitting a 9:1 selector or promoting a memory principle would overfit this development stream and cannot improve recovery success over always selecting compensation.

## Integrity

Agent feature rows passed nested Oracle-field rejection. Candidate winners remain evaluator-only. The experiment used no API calls, rendering, memory writes, or principle generation. It does not authorize a held-out run.

## Next step

Use a new label-blind development coverage protocol that collects additional operational stochastic-noise failures without selecting seeds by candidate outcome. Preserve this run unchanged. Do not tune a threshold on the unique retry winner.

## Reproduction

```bash
python scripts/analyze_probemem_paired_utility.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_paired_utility_20260731T172244Z_44bc5d206ddf"
```
