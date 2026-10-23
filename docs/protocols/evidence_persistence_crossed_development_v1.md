# Evidence persistence: crossed-context development v1

Status: frozen before collection. Authorized scope: the user's continuing
CCF A publication research objective; this is a new causal evidence design,
not a relaxation or rerun of any previous protocol.

## Question and estimand

Does probe-grounded correction depend on persistence of the execution context
between evidence acquisition and intervention? A diagnostic label can remain
"stable bias" while its direction or magnitude changes across this boundary.

Use the existing MetaWorld push-v3 policy, existing four bias conditions, the
registered 64-step repeated probe, and unchanged correction construction.
Execute every seed 8000--8015 crossed with every source context s and target
context t in {fault_01,...,fault_04}. Each source supplies one Agent-visible
probe. Write its correction plan before ANY target outcome for that seed.
Execute probe compensation and uncorrected control for all 16 pairs per seed.
The uncorrected target rollout is reused across source rows with explicit cache
provenance because it never consumes source evidence. All branches are seeded
reset-matched. Each unique branch owns fresh environment and policy objects.

Let Y_m(k,s,t) be binary task success for method m and task seed k. For each
method, aligned utility is the diagonal mean over s=t, and independent-context
utility is the full 4x4 mean, including the diagonal. The primary interaction is

    D = (aligned_probe - aligned_uncorrected)
        - (independent_probe - independent_uncorrected).

Both designs have exactly uniform source and target marginals for each seed.
An off-diagonal-only comparison is NOT the independent design. The uncorrected
contrast must be exactly zero since it is source-independent; otherwise the
implementation fails its negative-control integrity check.

This evaluator-only audit includes ALL task states, regardless of success. It
does not collect a failed-initial population or claim a recovery rate. Skipping
successful states would change the context marginals and invalidate the primary
causal comparison. The two methods test whether measured bias compensation
transports, not a new selective policy, LLM, or memory method.

## Frozen execution

- Exactly 16 task seeds, 64 source probes, 512 logical method/context rows.
- At most 320 physical task rollouts: 16x(4 uncorrected + 16 compensation).
- At most 164,096 physical steps: 64x64 probe + 320x500 task steps.
- Each logical probe-and-execution path uses at most 564 steps; uncorrected
  paths use at most 500. All paths are evaluator measurements.
- Unsupported compensation is retained as a zero-step failure, never dropped.
- Seeds 8016--8199 are reserved. No historical or unused stopped stream runs.
- No fitting, threshold change, API call, memory write, or policy-weight update.
- Commit protocol, config, implementation and tests before generating a manifest.
  Manifest hashes tracked Python sources and inputs and records package versions.
  Require clean committed implementation. Only one manifest/run for this protocol;
  a failure is preserved and not restarted or replaced.
- Journal evidence/decisions before outcomes and flush records at seed boundaries.
  A failure leaves an INCOMPLETE status and completed records intact.

## Analysis and feasibility gate

Average within each task seed first; bootstrap the 16 whole task seeds with
10,000 draws and RNG seed 20261013. Never count 512 rows as independent samples.
Report both method utilities, D, per-seed contrasts, 95% percentile interval,
abstention counts, logical and physical steps, state-hash and timing integrity.

Gate: all 16 complete clusters, D >= 0.10, aligned probe benefit >= 0.10,
cluster interval lower bound > 0, and zero integrity errors. These are
development feasibility criteria, not a conference publication threshold.
Failure cannot tune the bias set, correction rule, or seed population. Passage
supports only further development of an evidence-validity mechanism under a new
protocol. Independent streams, multi-task tests, strong adaptive baselines, and
scientific novelty remain outstanding for a publication claim.
