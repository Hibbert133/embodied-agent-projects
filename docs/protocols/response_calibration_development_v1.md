# Independently calibrated continuous response: qualification v1

Freeze before any new measurements. This is a standard affine calibration
baseline and a prerequisite identification study, not a new algorithm, task
performance study, adaptive policy, or publication claim. Prior task-evaluation
data and all reserved seeds are excluded from fitting and qualification.

## Explicit calibration assumption and costs

The laboratory actuator is in a known nominal zero-bias condition, with the
same per-step xyz Gaussian execution noise std 0.05. The operator commands
known constant xy offsets in addition to the existing continuous 16-step
probe. These offsets are visible commanded inputs, not hidden fault labels.
This requires access to a nominal calibration regime; it is not automatically
available in deployment and cannot be assumed free. No executed noisy action
is exposed to the model. MetaWorld push-v3 and initial robot pose remain fixed.

Training: seeds 8900--8907, each crossed with all nine known command offsets
in {-0.2,0,+0.2}^2. Qualification: independent seeds 8908--8915 crossed with
{-0.15,0,+0.15}^2. Every sequence has its own single initial environment and
noise reset, then sixteen continuous steps with no reset between directions.
Every trial is retained. No policy rollout, task-outcome selection, threshold
tuning, repeated attempt, or coefficient sweep. Reserve seeds 8916--9099.

72 training trials + 72 qualification trials cost 2,304 environment steps
and 144 explicit environment resets. Both training and qualification costs
must be disclosed in a later task study. Collection order is seed-major and
lexicographic xy offset. A terminated/successful/incomplete calibration probe
fails the collection; preserve it rather than substitute another state.

## Frozen fit and held-apart qualification

For each trajectory, collect the 32-dimensional vector of observed gripper xy
positions after each step relative to its initial position. Fit the affine
response f = nominal + sensitivity * commanded_offset by ordinary least squares
over the 72 training trials. Unknown online offset is then estimated by least
squares inversion of that fixed 32x2 sensitivity matrix. No ridge, feature
selection, model-order search, qualification refit, or nonlinear tuning.

Also retain mean training features for each of the nine command offsets as a
nearest-centroid baseline. Both methods receive the same calibration data.
Fit and save the model before reading any qualification trial. Predictions
consume only visible trajectory features and the frozen model; the known
qualification offset remains outside inference and is used only for scoring.
The deployment API separately requires the nominal probe program and has no
hidden-offset argument.

Calibration applies known offsets in the command; future deployment injects
an unknown execution offset after the command. Their equivalence here assumes
additive input offsets, the same actuator dynamics, no pre-noise command
saturation, and unchanged initial robot-state distribution. This study does
not test altered friction, poses, robots, controllers, or stale calibration.

## Qualification metrics and gate

Report mean, median, and 90th-percentile Euclidean offset error for affine and
nearest-centroid inference, all 72 predictions, per-seed means, feature
reconstruction error, response singular values, and all physical costs.
Percentiles use NumPy's linear interpolation. Affine passes qualification only
if mean error <=0.05 and 90th-percentile error <=0.10, with complete data and
all source, chronology, visible-input, and budget audits passing. These fixed
engineering tolerances are not confidence bounds or a powered superiority
test. Nearest-centroid results are descriptive; no best-method selection.

Failure is preserved without fitting anything to qualification data. A pass
permits considering a separately preregistered task-utility comparison on new
seeds, retaining no-probe, probe-motion, online-identification, and matched-
calibration baselines. It does not authorize reuse of qualification data as
task evaluation or establish a new contribution. API and memory writes are zero.
