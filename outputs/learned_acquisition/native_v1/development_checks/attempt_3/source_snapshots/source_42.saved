"""Evaluator-only three-family between-episode changes and continuous step noise."""
import hashlib
import math
import numpy as np

FAMILIES = ("BIAS", "COLUMN_Y", "DEADZONE")
SCHEDULES = ("UNCHANGED", "ABRUPT", "GRADUAL")
TASKS = ("push-v3", "reach-v3", "door-open-v3")


def states(seed, family):
    rng = np.random.default_rng(seed)
    if family == "BIAS":
        result = []
        for _ in range(2):
            angle = rng.uniform(-math.pi, math.pi); radius = rng.uniform(.12, .18)
            result.append({"matrix_xy": np.eye(2).tolist(), "bias_xy": [float(radius*math.cos(angle)), float(radius*math.sin(angle))], "deadzone_xy": [0., 0.]})
        return result
    if family == "COLUMN_Y":
        first = [float(rng.uniform(.9, 1.1)), float(rng.uniform(-.03, .03))]
        bias = rng.uniform(-.08, .08, 2).tolist()
        sign = float(rng.choice([-1., 1.]))
        return [{"matrix_xy": [[first[0], float(rng.uniform(-.05, .05))], [first[1], float(rng.uniform(.9, 1.1))]], "bias_xy": bias, "deadzone_xy": [0., 0.]},
                {"matrix_xy": [[first[0], float(sign*rng.uniform(.6, .8))], [first[1], float(rng.uniform(.55, .7))]], "bias_xy": list(bias), "deadzone_xy": [0., 0.]}]
    if family == "DEADZONE":
        matrix = np.array([[1., rng.uniform(-.15, .15)], [rng.uniform(-.15, .15), 1.]]).tolist()
        bias = rng.uniform(-.12, .12, 2).tolist()
        return [{"matrix_xy": matrix, "bias_xy": bias, "deadzone_xy": rng.uniform(.02, .08, 2).tolist()},
                {"matrix_xy": [list(row) for row in matrix], "bias_xy": list(bias), "deadzone_xy": rng.uniform(.18, .25, 2).tolist()}]
    raise ValueError("unknown evaluator fault family")


def fraction(schedule, episode):
    if schedule == "UNCHANGED": return 0.
    if schedule == "ABRUPT": return float(episode >= 6)
    if schedule == "GRADUAL": return float(np.clip((episode-2)/7, 0, 1))
    raise ValueError("unknown evaluator schedule")


def blend(a, b, weight):
    return {key: ((1-weight)*np.asarray(a[key])+weight*np.asarray(b[key])).tolist() for key in ("matrix_xy", "bias_xy", "deadzone_xy")}


def population(phase):
    if phase == "SMOKE":
        a = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}
        b = {**a, "bias_xy": [-.14, .1]}
        return [{"stream": 0, "family_oracle": "BIAS", "schedule_oracle": "ABRUPT_SMOKE", "cases": [
            {"episode": i, "task": TASKS[(i+1)%3], "seed": 16000+i, "fraction_oracle": float(i >= 3), "fault_oracle": a if i < 3 else b} for i in range(6)]}]
    if phase != "MAIN": raise ValueError("unknown frozen phase")
    rows = []
    for replicate in range(4):
        for fi, family in enumerate(FAMILIES):
            for si, schedule in enumerate(SCHEDULES):
                stream = len(rows); a, b = states(62001+stream, family)
                cases = [{"episode": i, "task": TASKS[(i+replicate+fi+si)%3], "seed": 17000+12*stream+i,
                          "fraction_oracle": fraction(schedule, i), "fault_oracle": blend(a, b, fraction(schedule, i))} for i in range(12)]
                rows.append({"stream": stream, "family_oracle": family, "schedule_oracle": schedule,
                             "generation_seed_oracle": 62001+stream, "endpoint_states_oracle": [a, b], "cases": cases})
    return rows


class ChronologicalNoise:
    def __init__(self, seed):
        rng_seed = int(np.random.SeedSequence([seed, 47001]).generate_state(1)[0])
        self._values = np.random.default_rng(rng_seed).normal(0, .05, (500, 3)).astype("<f4")
        self._values.setflags(write=False); self._cursor = 0; self._past = hashlib.sha256()
        self.commitment_oracle = {"full_sha256": hashlib.sha256(self._values.tobytes()).hexdigest(), "rows": 500, "namespace": 47001, "dtype": "little-endian-float32"}

    @property
    def cursor(self): return self._cursor

    def past_hash(self): return self._past.copy().hexdigest()

    def consume(self):
        if self._cursor >= 500: raise ValueError("single case noise exhausted")
        row = self._values[self._cursor].copy(); self._past.update(row.tobytes()); self._cursor += 1
        return row


def deterministic_action(sent, fault):
    command = np.asarray(sent, np.float32)
    if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
        raise ValueError("bounded finite sent action required")
    matrix = np.asarray(fault["matrix_xy"], np.float32); bias = np.asarray(fault["bias_xy"], np.float32); zone = np.asarray(fault["deadzone_xy"], np.float32)
    if matrix.shape != (2, 2) or bias.shape != (2,) or zone.shape != (2,) or not all(np.isfinite(v).all() for v in (matrix, bias, zone)) or np.any(zone < 0) or np.any(zone >= 1):
        raise ValueError("invalid private fault")
    value = command.copy(); latent = matrix @ command[:2]+bias
    value[:2] = np.sign(latent)*np.maximum(np.abs(latent)-zone, 0)/(1-zone)
    return value


def apply_fault(sent, fault, tape):
    if type(tape) is not ChronologicalNoise: raise ValueError("private continuous tape required")
    value = deterministic_action(sent, fault); value[:3] += tape.consume()
    return np.clip(value, -1, 1)
