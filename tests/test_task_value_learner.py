import copy
from dataclasses import asdict
import unittest
import numpy as np

from scripts.run_task_value_learner import CONFIG, read, validate, decode, encode, evidence
from scripts.audit_task_value_learner import equation, checked_pre, policy_checks
from src.probe.task_value_learner import (BranchRow, KernelModel, ValueEvidence, fit_policy,
                                        pre_choice, post_choice, training)


def visible(probe=0, valid=None, offset=0.):
    steps = 6 + probe
    observations = [tuple([offset + i * .001, .6, .2] + [0.] * 36) for i in range(steps + 1)]
    commands = [(0., 0., 0., 0.)] * 6
    commands += [v for v in ((.4, 0., 0., 0.), (-.4, 0., 0., 0.), (0., .4, 0., 0.), (0., -.4, 0., 0.)) for _ in range(probe // 4)]
    point = (1., 0., 0., 0., 1., 0.)
    return ValueEvidence("push-v3", observations, commands, [(0., 0., 0., 0.)] * 6 + [None] * probe,
                         point, probe, 500 - steps, valid, point if valid else None, .0001 if probe else None)


def rows(groups=4):
    result = []
    for group in range(groups):
        pre = visible(offset=group * .01)
        post = {n: visible(n, False, group * .01) for n in (8, 16)}
        outcomes = {"CACHE_CONTINUE": {"success": True, "stopped": False, "steps": 100, "loss": 100}}
        for n in (8, 16):
            outcomes[f"MID{n}_WIDE"] = {"success": False, "stopped": True, "steps": 6 + n, "loss": 500}
            outcomes[f"MID{n}_WIDE_KEEP"] = {"success": True, "stopped": False, "steps": 16 + n, "loss": 16 + n}
        result.append(BranchRow(f"group{group}", group, pre, post, outcomes))
    return result


class Constant:
    def __init__(self, *values):
        self.values = np.asarray(values)

    def predict(self, features):
        return self.values


class TaskValueEvidenceTest(unittest.TestCase):
    def test_privileged_and_future_fields_fail_closed(self):
        for field in ("seed", "scenario", "group", "operator_id_oracle", "rng_state", "future_outcome"):
            value = asdict(visible()); value[field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                ValueEvidence.from_dict(value)
        value = asdict(visible()); value["fit_valid"] = True
        with self.assertRaises(ValueError):
            ValueEvidence.from_dict(value)

    def test_stage_end_budget_and_measurement_program_are_checked(self):
        for field, replacement in (("remaining_steps", 500), ("probe_steps", True), ("observations", [])):
            value = asdict(visible()); value[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                ValueEvidence.from_dict(value)
        value = asdict(visible(8, True)); value["commands"] = [(0., 0., 0., 0.)] * 14
        with self.assertRaises(ValueError):
            ValueEvidence.from_dict(value)

    def test_nonfinite_values_and_invalid_inverse_cannot_be_approved(self):
        value = asdict(visible()); value["old_parameters"] = [float("nan")] * 6
        with self.assertRaises(ValueError):
            ValueEvidence.from_dict(value)
        value = asdict(visible(8, True)); value["fit_parameters"] = [0.] * 6
        with self.assertRaises(ValueError):
            ValueEvidence.from_dict(value)

    def test_future_policy_rows_and_oracle_fields_do_not_change_extraction(self):
        e = visible(8, True)
        record = {"task": e.task, "initial": {"observation": list(e.observations[0])},
                  "source_cache": {"matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [0., 0.]},
                  "trace": [{"command": c, "raw_policy": raw, "after": {"observation": obs, "success": False, "terminated": False, "truncated": False}, "executed_action_oracle": [99.] * 4}
                            for c, raw, obs in zip(e.commands, e.raw_policy, e.observations[1:])],
                  "decisions": [{"at_host_calls": 14, "fit": {"valid": True, "matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [0., 0.], "residual_rmse_m": .0001}}]}
        before = evidence(record, 8)
        record["trace"].append({"after": {"observation": [999.] * 39}, "future_outcome": True})
        record["seed"] = 999; record["operator_id_oracle"] = "different"
        self.assertEqual(asdict(before), asdict(evidence(record, 8)))

    def test_only_new_fit_can_change_post_choice(self):
        self.assertEqual(post_choice(visible(8, True), Constant(-.5))["action"], "UPDATE")
        self.assertEqual(post_choice(visible(8, True), Constant(.5))["action"], "KEEP")
        self.assertEqual(post_choice(visible(8, True), Constant(0.))["action"], "KEEP")
        self.assertEqual(post_choice(visible(8, False), Constant(-.5))["action"], "KEEP")
        with self.assertRaises(ValueError):
            post_choice(visible(), Constant(-.5))

    def test_saved_predictions_change_acquisition_and_ties_keep_cost(self):
        self.assertEqual(pre_choice(visible(), Constant(-.5, -.1))["action"], "PROBE8_WIDE")
        self.assertEqual(pre_choice(visible(), Constant(-.1, -.5))["action"], "PROBE16_WIDE")
        self.assertEqual(pre_choice(visible(), Constant(0., .5))["action"], "CACHE_CONTINUE")


class TaskValueTrainingTest(unittest.TestCase):
    def test_configuration_cannot_silently_change_cost_or_fold_semantics(self):
        config = read(CONFIG); validate(config)
        for key, changed in (("loss_scale", 100), ("ridge", .1), ("outer_split", "RANDOM_ROWS"), ("new_api_calls", 1)):
            altered = {**config, key: changed}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(altered)

    def test_group_overlap_and_inconsistent_branch_history_are_rejected(self):
        with self.assertRaises(ValueError):
            fit_policy(rows(), excluded=(3,))
        with self.assertRaises(ValueError):
            training([rows()[0], rows()[0]])
        row = encode(rows()[0]); row["post"]["8"]["observations"] = [[1.] * 39, *row["post"]["8"]["observations"][1:]]
        with self.assertRaises(ValueError):
            decode(row)

    def test_outer_group_has_no_effect_on_any_fitted_quantity(self):
        source = rows()
        first = fit_policy(source[:3], excluded=(3,))
        changed = copy.deepcopy(source)
        changed[-1].outcomes["CACHE_CONTINUE"].update(success=False, steps=500, loss=500)
        second = fit_policy(changed[:3], excluded=(3,))
        self.assertEqual(first["pre"].saved(), second["pre"].saved())
        for inner in first["inner"]:
            self.assertNotIn(f"group{inner['excluded_group']}", inner["training_case_ids"])
            self.assertNotIn("group3", inner["training_case_ids"])

    def test_post_choice_coupling_changes_pre_acquisition(self):
        policy = fit_policy(rows())
        self.assertEqual(pre_choice(visible(), policy["pre"])["action"], "PROBE8_WIDE")
        self.assertEqual(pre_choice(visible(), policy["direct"])["action"], "CACHE_CONTINUE")
        self.assertEqual(post_choice(visible(8, False), policy["post"][8])["action"], "KEEP")
        for inner in policy["inner"]:
            for decision in inner["decisions"]:
                self.assertTrue(all(c["selected_method"].endswith("_KEEP") for c in decision["choices"].values()))

    def test_kernel_equation_round_trip_and_invalid_artifact(self):
        x = np.asarray([[0., 1.], [1., 2.], [2., 3.]])
        y = np.asarray([[0.], [1.], [2.]])
        model = KernelModel.fit(x, y)
        restored = KernelModel.from_saved(model.saved())
        np.testing.assert_allclose(model.predict(x[1]), restored.predict(x[1]), rtol=0, atol=0)
        distance = ((model.support[:, None] - model.support[None, :]) ** 2).sum(axis=2)
        kernel = np.exp(-distance / (2 * model.bandwidth_squared))
        np.testing.assert_allclose((kernel + np.eye(3)) @ model.weights, y - y.mean(axis=0), atol=1e-12)
        invalid = model.saved(); invalid["scale"][0] = 0
        with self.assertRaises(ValueError):
            KernelModel.from_saved(invalid)

    def test_independent_audit_rejects_wrong_weights_and_swapped_action(self):
        x = [[0.], [1.], [2.]]; y = [[0., -.2], [.2, -.4], [.4, -.6]]
        model = KernelModel.fit(x, y).saved()
        equation(model, x, y)
        altered = copy.deepcopy(model); altered["weights"][0][0] += .1
        with self.assertRaises(ValueError):
            equation(altered, x, y)
        fitted = fit_policy(rows())
        decision = pre_choice(visible(), fitted["pre"])
        checked_pre(fitted["pre"].saved(), visible(), decision)
        decision["action"] = "CACHE_CONTINUE"
        with self.assertRaises(ValueError):
            checked_pre(fitted["pre"].saved(), visible(), decision)

    def test_independent_audit_checks_inner_exclusion_and_target_equations(self):
        source = rows(); policy = fit_policy(source)
        saved = {"pre": policy["pre"].saved(), "post": {str(n): m.saved() for n, m in policy["post"].items()},
                 "direct": policy["direct"].saved(), "inner": policy["inner"], "training_case_ids": policy["training_case_ids"]}
        self.assertEqual(policy_checks(saved, source), 12)
        saved["inner"][0]["training_case_ids"].append("group0")
        with self.assertRaises(ValueError):
            policy_checks(saved, source)


if __name__ == "__main__":
    unittest.main()
