# Reproduction Commands

Run all commands from the repository root with Python 3.10.

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
python scripts/run_active_diagnostic_probes.py
python scripts/evaluate_planar_bias_recovery.py --seeds 260 261 262 263 264 265 266 267 268 269 --bias-x 0.14 --bias-y -0.14 --max-steps 500 --output-dir outputs/planar_bias_pilot/xpos014_yneg014_heldout
python scripts/evaluate_horizon_utility.py --run-dir outputs/online_utility_agent/glm51_utility_dev
```

## Online model experiments

Configure a newly issued credential once. Windows DPAPI encrypts the local file for
the current Windows user, and Git ignores it. Do not reuse a key exposed in chat.

```powershell
.\scripts\configure_agent_api.ps1 -Model glm-5.1 -BaseUrl https://api.modelarts-maas.com/anthropic
.\scripts\check_agent_api_config.ps1
```

After setup, online wrappers load and clear the process credential automatically:

```powershell
.\scripts\run_online_utility_agent.ps1 -Model glm-5.1 -RunName glm51_utility_dev
.\scripts\run_budgeted_autoresearch.ps1 -Model glm-5.1
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
