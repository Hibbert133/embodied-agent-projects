# Reproduction Commands

Run all commands from the repository root with Python 3.10.

## Frozen Phase-2 evidence allocation

Generate a new immutable manifest only from a clean committed worktree. Never
reuse the literal run ID below for changed code or dependencies.

```powershell
python scripts/generate_heldout_manifest.py
python scripts/run_frozen_heldout_allocation.py --manifest outputs/heldout_allocation/runs/<new-run-id>/manifest.json
python scripts/plot_heldout_allocation.py --run-dir outputs/heldout_allocation/runs/<new-run-id> --output outputs/figures/evidence_allocation_frontier.png
```

The completed registered run is
`heldout_20260731T015847Z_a39271db862f`; its source commit is
`c656ad787e5d77174ecbf8e76cdaf9c1b6ac1dab`.

## Installation and baseline

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/check_install.py
python scripts/demo_push.py --output outputs/push_demo.mp4 --seed 42 --max-steps 500
python scripts/evaluate_push.py --num-episodes 10 --seed-start 100 --max-steps 500 --output-csv outputs/push_evaluation.csv --trajectory-dir outputs/push_trajectories
```

## Controlled perturbations

```powershell
python scripts/sweep_perturbations.py --num-episodes 20 --seed-start 100 --max-steps 500 --output-csv outputs/perturbation_sweep.csv --summary-csv outputs/perturbation_summary.csv
python scripts/render_day2_5_representatives.py
python scripts/validate_schema_v2_trajectories.py
```

## Active evidence and bounded interventions

```powershell
python scripts/run_active_evidence_campaign.py --config configs/campaigns/active_evidence_smoke.json
python scripts/validate_active_evidence_selection.py --config configs/campaigns/active_evidence_glm52_dev5.json
python scripts/analyze_active_evidence_campaign.py --run-dir outputs/campaigns/active_evidence_glm52_dev5_v1
python scripts/run_active_diagnostic_probes.py
python scripts/evaluate_planar_bias_recovery.py --seeds 260 261 262 263 264 265 266 267 268 269 --bias-x 0.14 --bias-y -0.14 --max-steps 500 --output-dir outputs/planar_bias_pilot/xpos014_yneg014_heldout
python scripts/evaluate_horizon_utility.py --run-dir outputs/online_utility_agent/glm51_utility_dev
```

The campaign command is resumable: completed stable job IDs are loaded from
`run_ledger.jsonl`. Its configuration declares maximum jobs, environment steps,
API calls, and wall time before execution. The included smoke configuration is
integration evidence only, not a performance benchmark.

## Online model experiments

Configure a newly issued credential once. Windows DPAPI encrypts the local file for
the current Windows user, and Git ignores it. Do not reuse a key exposed in chat.

```powershell
.\scripts\configure_agent_api.ps1 -Model glm-5.2 -BaseUrl https://api.modelarts-maas.com/anthropic
.\scripts\check_agent_api_config.ps1
```

After setup, online wrappers load and clear the process credential automatically:

```powershell
.\scripts\run_active_evidence_campaign.ps1 -Config configs\campaigns\active_evidence_glm52_pilot.json -ApiTimeout 300
.\scripts\run_online_utility_agent.ps1 -Model glm-5.2 -RunName glm52_utility_dev
.\scripts\run_budgeted_autoresearch.ps1 -Model glm-5.2
```

## Engineering validation

```powershell
python -m unittest discover -s tests -v
python -m pip check
python scripts/check_tracked_secrets.py
git diff --check
```

Quantitative claims must be read from committed CSV/JSONL artifacts and their linked
reports. Do not substitute values printed in documentation examples.
