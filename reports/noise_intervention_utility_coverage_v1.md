# Noise Intervention Utility Coverage v1

The label-blind collection stopped after reaching 20 paired-comparable
stochastic-noise failures. It required 59 sequential initial units (seeds
430--488) under a fixed maximum of 60.

- compensation preferred: 12/20;
- retry preferred: 8/20;
- both candidates recovered 8/20;
- post-probe mechanism routing aligned with preferred utility in 9/20;
- 13 belief changes produced 6 better and 7 worse selections.

No threshold was fitted. Preregistered ROC AUC values were: phase inconsistency
0.469, temporal uncertainty 0.469, probe bias std norm 0.698, relative bias std
0.542, probe residual 0.510, and sign disagreement 0.510. The earlier n=7 AUC
0.75 signals did not replicate at larger coverage. Probe bias variability is the
only remaining single-feature candidate, but AUC 0.698 is insufficient for a
strong selector claim without a separately frozen rule and new evaluation.

This result strengthens the negative conclusion: mechanism correctness and the
current aggregate uncertainty features do not reliably identify intervention
utility. P2 memory remains blocked.

Run: `development_20260731T035004Z_ed696b94484e`, source commit
`ed696b94484ee10b7cb2ad633c5c9d2fa9d8bbf7`.
