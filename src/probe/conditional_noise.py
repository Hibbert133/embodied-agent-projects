"""Evaluator-owned immutable prefix/future noise, generated before interaction.

This source never resets, reseeds or rewinds during a trajectory. Candidate
controllers receive observed samples, not this object or its commitments.
"""
import hashlib
import numpy as np


class ConditionalNoiseTape:
    def __init__(self, task_seed, task_index, future_index):
        if any(type(v) is not int for v in (task_seed, task_index, future_index)) or task_seed < 0 or task_index not in (0, 1, 2) or future_index not in range(4):
            raise ValueError("registered evaluator noise identity required")
        prefix_seed = int(np.random.SeedSequence([task_seed, task_index, 46003]).generate_state(1)[0])
        future_seed = int(np.random.SeedSequence([task_seed, task_index, 46005, future_index + 1]).generate_state(1)[0])
        prefix = np.random.default_rng(prefix_seed).normal(0, .05, (8, 3)).astype("<f4")
        future = np.random.default_rng(future_seed).normal(0, .05, (492, 3)).astype("<f4")
        values = np.concatenate((prefix, future)); values.setflags(write=False)
        self._values = values; self._cursor = 0; self._past = hashlib.sha256()
        self.commitment_oracle = {"prefix_sha256": hashlib.sha256(prefix.tobytes()).hexdigest(),
                                  "future_sha256": hashlib.sha256(future.tobytes()).hexdigest(),
                                  "full_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                                  "prefix_steps": 8, "future_steps": 492, "dtype": "little-endian-float32"}

    @property
    def cursor(self):
        return self._cursor

    def past_hash(self):
        return self._past.copy().hexdigest()

    def consume(self):
        if self._cursor >= 500:
            raise ValueError("evaluator noise tape exhausted")
        value = self._values[self._cursor].copy()
        self._past.update(value.tobytes()); self._cursor += 1
        return value


def apply_affine_tape(command, matrix_xy, bias_xy, tape):
    """Evaluator injection; private mapping and future noise never enter a fit."""
    if type(tape) is not ConditionalNoiseTape:
        raise ValueError("registered immutable evaluator tape required")
    sent = np.asarray(command, np.float32)
    matrix = np.asarray(matrix_xy, np.float32); bias = np.asarray(bias_xy, np.float32)
    if sent.shape != (4,) or matrix.shape != (2, 2) or bias.shape != (2,) or not all(np.isfinite(v).all() for v in (sent, matrix, bias)) or np.any(np.abs(sent)>1):
        raise ValueError("finite registered actuator shapes required")
    actual = sent.copy(); actual[:2] = matrix @ actual[:2] + bias; actual[:3] += tape.consume()
    return np.clip(actual, -1, 1)
