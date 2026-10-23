from dataclasses import dataclass, replace
import unittest
import numpy as np
from src.probe.continuous import StepObservation, collect_continuous, fit_local_response, symmetric_program


class LiveLinearPlant:
    def __init__(self, end_at=None, status="terminated"):
        self.position = np.array([.1, -.2, .3])
        self.velocity = np.array([.001, -.002])
        self.inertia = np.array([[.45,.05],[-.03,.6]])
        self.response = np.array([[.02,.004],[-.003,.025]])
        self.bias = np.array([.15,-.2])
        self.calls = 0
        self.end_at, self.status = end_at, status

    def reset(self):
        raise AssertionError("reset capability must never be used")

    def observation(self, **flags):
        return StepObservation(tuple(self.position), flags.get("terminated",False),
                               flags.get("truncated",False), flags.get("success",False))

    def step(self, command):
        self.calls += 1
        self.velocity = self.inertia @ self.velocity + self.response @ (command[:2]+self.bias)
        self.position[:2] += self.velocity
        return self.observation(**{self.status: self.calls == self.end_at})


class ContinuousProbeTest(unittest.TestCase):
    def collect(self, plant, commands=None, **kwargs):
        return collect_continuous(plant.step, plant.observation(), commands or symmetric_program(),
                                  remaining_budget=kwargs.pop("remaining_budget",516), **kwargs)

    def test_continuity_final_handoff_and_exact_accounting(self):
        plant = LiveLinearPlant()
        evidence = self.collect(plant)
        self.assertEqual((plant.calls,evidence.steps,evidence.requested_steps), (16,16,16))
        self.assertEqual(evidence.stop_reason,"PROGRAM_COMPLETE")
        for left,right in zip(evidence.transitions,evidence.transitions[1:]):
            self.assertEqual(left.after,right.before)
        self.assertEqual(evidence.final.observation,tuple(plant.position))
        plant.step(np.zeros(4))
        self.assertEqual(plant.calls,17)  # task continues from the live final state

    def test_recovers_cross_coupled_dynamic_response_from_commands_only(self):
        plant = LiveLinearPlant()
        fit = fit_local_response(self.collect(plant))
        self.assertTrue(fit.valid)
        np.testing.assert_allclose(fit.bias_in_command_units,plant.bias,atol=1e-10)
        np.testing.assert_allclose(fit.response,plant.response,atol=1e-10)
        np.testing.assert_allclose(fit.inertia,plant.inertia,atol=1e-10)
        self.assertLess(fit.residual_rmse,1e-12)

    def test_reserve_and_bad_program_fail_before_any_steps(self):
        for program,budget in ((symmetric_program(),515), ([(float("nan"),0,0,0)],516),
                               ([(2,0,0,0)],516), ([(0,0)],516)):
            plant = LiveLinearPlant()
            with self.assertRaises(ValueError):
                self.collect(plant,program,remaining_budget=budget)
            self.assertEqual(plant.calls,0)

    def test_terminal_truncated_and_success_stop_without_extra_step(self):
        for flag in ("terminated","truncated","success"):
            plant = LiveLinearPlant(end_at=5,status=flag)
            evidence = self.collect(plant)
            self.assertEqual(evidence.steps,5)
            self.assertEqual(plant.calls,5)
            self.assertEqual(evidence.stop_reason,flag.upper())
            self.assertFalse(fit_local_response(evidence).valid)

    def test_rank_deficient_design_fails_without_fabricated_correction(self):
        fit = fit_local_response(self.collect(LiveLinearPlant(),[(.2,0,0,0)]*16))
        self.assertFalse(fit.valid)
        self.assertEqual(fit.reason,"UNIDENTIFIABLE_DESIGN")
        self.assertIsNone(fit.bias_in_command_units)

    def test_discontinuous_or_forged_final_state_rejected(self):
        evidence = self.collect(LiveLinearPlant())
        rows = list(evidence.transitions)
        rows[3] = replace(rows[3],before=(0.,0.,0.))
        with self.assertRaisesRegex(ValueError,"discontinuous"):
            fit_local_response(replace(evidence,transitions=tuple(rows)))
        with self.assertRaisesRegex(ValueError,"final observation"):
            fit_local_response(replace(evidence,final=StepObservation((0.,0.,0.),False,False,False)))

    def test_visible_schema_rejects_unknown_fields_and_mutable_aliases(self):
        initial = [1.,2.,3.]
        state = StepObservation(initial,False,False,False)
        initial[0] = 9.
        self.assertEqual(state.observation,(1.,2.,3.))
        with self.assertRaises(TypeError):
            StepObservation((1.,2.,3.),False,False,False,context_oracle="bias")
        for value in ((True,2.,3.), (float("nan"),2.,3.), ("1",2.,3.)):
            with self.assertRaises(ValueError):
                StepObservation(value,False,False,False)

    def test_subclass_cannot_smuggle_evaluator_fields_into_evidence(self):
        @dataclass(frozen=True)
        class OracleObservation(StepObservation):
            context_oracle: str = "hidden"
        hidden = OracleObservation((0.,0.,0.),False,False,False)
        with self.assertRaises(ValueError):
            collect_continuous(lambda a: hidden,hidden,symmetric_program(),remaining_budget=516)
        with self.assertRaisesRegex(ValueError,"visible observation schema"):
            collect_continuous(lambda a: hidden,StepObservation((0.,0.,0.),False,False,False),
                               symmetric_program(),remaining_budget=516)


if __name__ == "__main__":
    unittest.main()
