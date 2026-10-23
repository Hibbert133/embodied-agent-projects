# ProbeMem Verifier Demo v1

## Result

Run `probemem_verifier_demo_20260804T092718Z_a158d7e53fbd` completed the
registered 50 fresh development units on seeds 4700--4749 and produced 21
operational failed initial rollouts. The immutable manifest ID is
`6288ba0c45d639fec3573b3bdd4763b31ed160a052aaa18ed50dc1e6b53a0b61` and
the source implementation commit is
`a158d7e53fbdb3e67d3ea44c34460ef625238690`.

The engineering integration completed with zero chronology, Oracle leakage,
future-memory, counterfactual-write, budget, random-namespace, invalid-ID, and
invalid-skill violations. The performance gate failed.

| Method | Accepted | Verifier calls | Overrides | Harmful selections |
|---|---:|---:|---:|---:|
| Frozen deterministic | 16/21 | 0 | 0 | 2 |
| Always-on verifier | 15/21 | 21 | 7 | 3 |
| Budgeted verifier | 15/21 | 11 | 2 | 3 |
| Evaluator-only Oracle | 18/21 | 0 | n/a | 0 |

The stream contained 10 exclusive-recovery cases. Frozen selected the accepted
candidate in 8/10, while Always-on and Budgeted each selected it in 7/10.

## Verifier and override behavior

Budgeted invoked the deterministic Bayesian verifier on 11/21 cases (52.4%).
This was a 47.6% verifier-call reduction relative to Always-on, narrowly missing
both registered 50% requirements. It made two action changes relative to
Frozen: zero were helpful, one was harmful, and one was an outcome tie. Override
precision was therefore 0/1 among non-tied changes.

The guard blocked nine proposed alternatives: one would have been helpful,
four harmful, and four tied. Thus the conservative guard prevented several bad
changes, but its applicability and posterior rules still authorized one harmful
change and blocked one helpful one. This does not support a Memory action-
improvement claim.

Mean final distance was 0.0870 for Frozen, 0.1014 for Always-on, and 0.0985 for
Budgeted. Total online-equivalent environment steps were 15,653, 16,054, and
16,067 respectively. Every operational method appended exactly 21 selected-
action records to its own chronology; no paired alternative entered memory.

The registered run used no GLM calls, tokens, retries, or timeouts. Local
deterministic verifier latency on admitted Budgeted cases was approximately
0.098 ms median and 0.104 ms p90. These values do not demonstrate live API
cost reduction.

## Gate evaluation

The gate failed for both substantive reasons:

* Budgeted call rate was 52.4%, above the maximum 50%.
* Route A failed because Budgeted recovered one fewer case than Frozen and had
  more harmful than helpful overrides.
* Route B failed because the call reduction was 47.6%, below 50%, even though
  Budgeted tied Always-on recovery.

The correct conclusion is:

> The verifier successfully entered the online action loop, but its memory
> applicability estimates were not sufficiently calibrated to improve recovery
> or meet the registered verifier budget.

No ambiguity-band, posterior, contradiction, coverage, or confidence parameter
will be tuned on seeds 4700--4749. Seeds 4750--4799 remain reserved. This result
does not authorize GLM execution, validation, held-out evaluation, principles,
another Skill, or a statistical performance claim.

## Reproduction and artifacts

The two-minute integration smoke is:

```powershell
.\.venv\Scripts\python.exe scripts\run_probemem_verifier_demo.py `
  --config configs\probemem_verifier\demo_v1.json `
  --smoke --verifier deterministic
```

The immutable run artifacts, analysis, three figures, and case page are under
`outputs/probemem_verifier_demo/runs/probemem_verifier_demo_20260804T092718Z_a158d7e53fbd/`.
`artifact_provenance.json` binds every file in that directory to its SHA-256,
run ID, manifest ID, and source commit without rewriting the raw trace.
