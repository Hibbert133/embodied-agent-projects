# ProbeMem v2 MuJoCo Endurance Blocker

## Motivation

The first ProbeMem Phase-C sequential comparison stopped after 54 of 60
method-cases with `MuJoCo engine error: Could not allocate memory`. A separate
development-only endurance preflight was registered to distinguish a long-run
environment lifecycle leak from host-level memory pressure. It made no API
calls, did not render, and did not touch held-out seeds.

## Registered preflight

- Protocol: `probemem_mujoco_endurance_preflight_v1`
- Source failed run: `probemem_phase_c_20260731T094646Z_9dc037acb04c`
- Source commit: `05f28f0809f911828eb41ebd0caf5d1cdd48f8ee`
- Development seeds: 760–779
- Intended construction cycles: 100
- Intended full rollouts: 20
- API calls: 0

## Actual result

The preflight failed before completing its first environment construction:

```text
status: FAILED
error: MemoryError: bad allocation
process RSS: 27.57 MB
available physical memory: 3663.68 MB
available system commit/pagefile: 200.56 MB
completed environment cycles: 0
```

The Python process was small and no repeated environment lifecycle had yet
occurred. The evidence therefore does not support a ProbeMem runner memory-leak
claim. It supports a narrower infrastructure diagnosis: the Windows host had
insufficient remaining commit capacity for MuJoCo arena allocation despite
several gigabytes of physically available RAM.

## Consequence

The incomplete Phase-C prefix remains non-claim-eligible. No new GLM run should
be launched under the current host state because environment initialization can
fail independently of the research method. The failed run and preflight must
not be overwritten.

Before another registered run:

1. restart the host or close high-commit applications manually;
2. verify that system available commit is materially above the observed
   200.56 MB failure state;
3. complete this no-API endurance preflight;
4. generate a new immutable Phase-C manifest;
5. execute the full chronological comparison from episode 1.

Changing the pagefile or terminating user processes is an operator decision,
not an automatic research-agent action.

## Commands

```powershell
$env:PROBEMEM_SOURCE_COMMIT='05f28f0809f911828eb41ebd0caf5d1cdd48f8ee'
.\.venv\Scripts\python.exe scripts\check_mujoco_endurance.py
```

Raw samples and summary:

- `outputs/probemem_v2/mujoco_endurance_preflight.csv`
- `outputs/probemem_v2/mujoco_endurance_preflight_summary.json`
