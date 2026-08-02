"""Infrastructure preflight: paired candidate order must not change outcomes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _run_verification, _seed  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _outcome(value: tuple[object, dict]) -> tuple[object, ...]:
    result, execution = value
    return (
        execution["verification_status"],
        result.success,
        result.steps,
        result.final_object_goal_distance,
        result.episode_return,
    )


def main() -> int:
    try:
        config = json.loads(
            (ROOT / "configs/probemem_v2/coverage_aware_memory_development_v1.json").read_text(
                encoding="utf-8"
            )
        )
        noise_std = float(
            json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))["noise_std"]
        )
        fault = {item.condition_id: item for item in get_conditions(noise_std)}["fault_05"]
        recovery_config = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        seed = 980
        env = create_push_environment(seed)
        try:
            initial = run_episode(
                env,
                create_push_policy(),
                seed=seed,
                episode_id=1,
                max_steps=500,
                perturbation=fault.build(),
                perturbation_seed=_seed(seed, 7601),
            )
        finally:
            env.close()
        probe = _probe_context(fault, seed, config, _seed(seed, 7602))
        verification_seed = _seed(seed, 7603)
        skills = (
            InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
            InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
        )

        def execute(order: tuple[InterventionSkill, ...]) -> dict[InterventionSkill, tuple[object, dict]]:
            return {
                skill: _run_verification(
                    seed=seed,
                    fault=fault,
                    skill=skill,
                    probe_context=probe,
                    recovery_config=recovery_config,
                    perturbation_seed=verification_seed,
                    max_steps=500,
                    initial_distance=initial.final_object_goal_distance,
                )
                for skill in order
            }

        forward = execute(skills)
        reverse = execute(tuple(reversed(skills)))
        for skill in skills:
            if _outcome(forward[skill]) != _outcome(reverse[skill]):
                raise RuntimeError(f"candidate order changed fresh outcome: {skill.value}")
        print("ProbeMem-ACR candidate order preflight: passed seed=980 orders=2 candidates=2")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
