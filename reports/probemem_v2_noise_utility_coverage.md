# ProbeMem Label-Blind Noise Utility Coverage

Run: `probemem_paired_utility_20260731T173200Z_aceee1a6eca2`
Manifest: `f191171b0dd485a9e6f08f232acf17205d687c5de52cf7a83ebb39d542e3f76f`
Source commit: `aceee1a6eca2d3313bb0b7c71629d0828b5ada3d`

## Actual collection

The label-blind stream scanned 58 initial noise units and stopped at the registered target of 20 complete operational pairs.

- Always compensation: 10/20 accepted.
- Always retry: 14/20 accepted.
- Oracle per-case skill choice: 16/20 accepted.
- Compensation-only recovery: 2.
- Retry-only recovery: 6.
- Both recover: 8.
- Neither recovers: 4.

## Research interpretation

This collection establishes real action-utility diversity. A perfect skill selector could improve recovery by 2/20 over always retry and 6/20 over always compensation. Unlike the previous mixed stream, retry now has six exclusive accepted recoveries and compensation has two.

Only eight cases are decisive for recovery selection. Exploratory feature ranking found `probe_relative_bias_std` as the strongest post-hoc univariate signal (direction `lower_favors_retry`, ROC AUC 0.917) on those eight cases. This is not a frozen selector result: direction was chosen post hoc, the negative class has only two cases, and no threshold was fit.

## Promotion decision

The data are sufficient to design a separately frozen development selector candidate, but not to promote Phase D, run held-out evaluation, or generate scientific-memory principles. The next selector must be preregistered and evaluated on fresh development seeds before any held-out use.

## Integrity

Stopping used candidate executability only and never read outcomes. Agent evidence passed nested Oracle rejection. API calls, rendering, memory writes, principle generation, and selector fitting were all zero.

## Reproduction

```bash
python scripts/analyze_probemem_noise_utility_coverage.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_paired_utility_20260731T173200Z_aceee1a6eca2"
```
