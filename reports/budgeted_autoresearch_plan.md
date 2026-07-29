# Budgeted Autoresearch for Failure-Aware Robotic Agents

## Research question

Can an online high-level Research Agent improve a leakage-safe robotic recovery
system by proposing bounded, falsifiable changes to active probing and skill
selection while using fewer environment interactions than random search?

This is an ENPIRE-inspired automatic research loop at the system-configuration
level. The model does not generate robot actions, controller code, or unrestricted
parameters. The low-level executor remains `SawyerPushV3Policy`.

## Architecture

1. Execution layer: MetaWorld `push-v3` and a fixed scripted policy.
2. Runtime Agent: failure evidence, active probes, typed recovery skills, verifier.
3. Research Agent: anonymized Agent-visible counterexamples and aggregate results;
   exactly two bounded configs per round.
4. Trusted evaluator: hidden faults and Oracle audit, never passed to either Agent.

The config controls probe length/magnitude, secondary-axis threshold, dominance
ratio, schedules, evidence detail, and abstention. Each failure receives at most
one recovery rollout.

## Two-week protocol

- Phase A: calibrate OOD noise, build five heterogeneous fault conditions, run
  actual skill counterfactuals, and verify leakage/budget contracts.
- Phase B: use six deterministically stratified tuning cases for two Research-Agent
  rounds (two candidates each) and four seeded random-search controls.
- Phase C: promote on frozen seeds 310–319, then evaluate once on held-out seeds
  320–329 and produce CSV-driven plots and videos.

## Evidence completed in this checkpoint

Noise calibration used seeds 300–309 and 90 real episodes. `std=0.60` was selected
by the registered rule (failure rate closest to 50%, then lower standard deviation,
with clipped-step fraction at most 0.5). It produced 6/10 successes and 40% failures.

The tuning benchmark contains 50 real initial episodes, 34 failures, and 170 actual
counterfactual recovery outcomes. Initial failure rates were 70%, 50%, 80%, 100%,
and 40% for anonymized `fault_01` through `fault_05`. Fault identities and parameters
exist only in Oracle audit artifacts.

On the deterministically stratified six-case pre-search reference, the fixed
default recovered 5/6 cases (83.3%) with 177.50 mean recovery environment steps.
The remaining Gaussian OOD case received an unsuitable repair and consumed a full
500-step rollout. This motivates, but does not yet demonstrate, improved abstention
by the online Research Agent.

## Reproduction

```powershell
.venv\Scripts\python.exe scripts\calibrate_noise_ood.py --seeds 300 301 302 303 304 305 306 307 308 309 --levels 0.25 0.30 0.35 0.40 0.45 0.50 0.55 0.60 0.70 --max-steps 500 --output-dir outputs\autoresearch\noise_calibration
.venv\Scripts\python.exe scripts\build_autoresearch_benchmark.py --seed-start 300 --num-seeds 10 --max-steps 500 --output-dir outputs\autoresearch\benchmark_tuning
.\scripts\run_budgeted_autoresearch.ps1 -Model glm-5.1 -BaseUrl https://api.modelarts-maas.com/anthropic -ApiTimeout 300
```

The PowerShell wrapper requests the API key through hidden input and removes it
afterward. Never place a credential in Git or logs.

## Online tuning result

The first completed GLM-5.1 tuning artifact contains two Research-Agent calls,
four proposed Research-Agent configs, and four seeded random-search configs. On
the six fixed cases, the best Research-Agent config (`research_r1_c1`) recovered
5/6 with 161.00 mean recovery environment steps. The best random config
(`random_03`) also recovered 5/6 with 159.83 mean steps. Under the registered
success-then-steps ordering, random search ranks first by 1.17 mean steps.

Both Research-Agent rounds predicted that changing the simultaneous-axis decision
boundary would recover the Gaussian OOD counterexample. It remained unsuccessful,
so the claimed 6/6 improvement was falsified. This indicates an identifiability
limitation in the current probe evidence, not evidence that a larger language
model or a broader search space would solve the problem.

The command was apparently launched repeatedly while using the original fixed
output directory. Earlier artifacts were overwritten, so `budget.json` certifies
only the final run's two API calls; total calls across the terminal session cannot
be recovered reliably. New runs use timestamped directories and refuse to overwrite
a completed result.

## Current limitation

Validation promotion, held-out evaluation, plots, and videos remain pending.
The tuning result does not show superiority over random search or general robotic-
agent performance. Before held-out evaluation, the smallest useful experiment is
to test an agent-visible probe-consistency feature that can separate persistent
bias from stochastic execution noise without reading injected fault labels.
