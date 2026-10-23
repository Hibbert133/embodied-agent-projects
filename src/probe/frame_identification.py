"""Nominal ARX / finite-frame system-identification baseline.

The estimator receives commanded inputs and visible observations only. It is
neither a confidence certificate nor a novel acquisition algorithm. Fault
injection belongs to the evaluator, outside this module.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import numpy as np
from src.probe.continuous import ContinuousEvidence, symmetric_program


METHODS = (
    "FIXED_A_PREFIX4", "FIXED_B_PREFIX4", "UNCORRECTED_PREFIX4",
    "MODEL_REPEAT8", "MODEL_REVERSE8", "MODEL_SYM16",
    "LEGACY_AFFINE16", "LEGACY_NEAREST16",
    "FIXED_A_REVERSE8", "FIXED_B_REVERSE8", "NO_PROBE",
)
ROTATIONS = (np.eye(2), np.array([[0., -1.], [1., 0.]]))


def program(method):
    if method not in METHODS:
        raise ValueError("unknown frame study method")
    if method == "NO_PROBE":
        return ()
    full = symmetric_program()
    if method.endswith("PREFIX4"):
        return full[:4]
    if method == "MODEL_REPEAT8":
        return full[:4] * 2
    if method.endswith("REVERSE8"):
        return full[:8]
    return full


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def transcript_hash(evidence, steps=None):
    # A prefix excludes the unavailable final observation of a longer probe.
    rows = evidence.transitions if steps is None else evidence.transitions[:steps]
    return canonical_hash([asdict(row) for row in rows])


def _design(evidence):
    if type(evidence) is not ContinuousEvidence or evidence.stop_reason != "PROGRAM_COMPLETE" or evidence.steps < 4:
        raise ValueError("requires a complete visible continuous probe")
    previous = evidence.transitions[0].before
    delta, commands = [], []
    for row in evidence.transitions:
        if row.before != previous or len(row.before) != 39 or len(row.after) != 39:
            raise ValueError("discontinuous visible trajectory")
        command = np.asarray(row.command, dtype=float)
        if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
            raise ValueError("invalid commanded input")
        if not np.isfinite(row.before + row.after).all():
            raise ValueError("invalid visible observation")
        delta.append(np.asarray(row.after[:2]) - row.before[:2])
        commands.append(command[:2])
        previous = row.after
    if previous != evidence.final.observation or evidence.steps != evidence.requested_steps:
        raise ValueError("probe final state or step count mismatch")
    delta = np.asarray(delta)
    return delta[:-1], np.asarray(commands)[1:], delta[1:]


@dataclass(frozen=True)
class NominalARX:
    inertia: tuple[tuple[float, float], ...]
    response: tuple[tuple[float, float], ...]
    intercept: tuple[float, float]
    samples: int
    training_trials: int
    design_rank: int
    scaled_condition: float
    residual_rmse: float
    training_digest: str

    def to_dict(self):
        return asdict(self)


def fit_nominal_arx(training):
    """Fit delta[t] = A delta[t-1] + B commanded_xy[t] + c.

    `training` is a sequence of nominal, known-command ContinuousEvidence.
    No task outcomes, fault labels, or qualification measurements are fitted.
    """
    if not training:
        raise ValueError("empty nominal training data")
    designs, targets = [], []
    for evidence in training:
        previous, command, observed = _design(evidence)
        designs.append(np.column_stack((previous, command, np.ones(len(observed)))))
        targets.append(observed)
    x, y = np.vstack(designs), np.vstack(targets)
    scale = np.sqrt(np.mean(x ** 2, axis=0))
    if np.any(scale < 1e-12):
        raise ValueError("nominal calibration lacks input rank")
    scaled = x / scale
    rank, condition = int(np.linalg.matrix_rank(scaled)), float(np.linalg.cond(scaled))
    if rank != 5 or condition > 1e6:
        raise ValueError("nominal calibration is numerically unidentifiable")
    coef = np.linalg.lstsq(scaled, y, rcond=None)[0] / scale[:, None]
    response = coef[2:4].T
    singular = np.linalg.svd(response, compute_uv=False)
    if singular[-1] < 1e-8 or singular[0] / singular[-1] > 1e6:
        raise ValueError("nominal planar response is not invertible")
    return NominalARX(tuple(map(tuple, coef[:2].T)), tuple(map(tuple, response)),
                      tuple(coef[4]), len(y), len(training), rank, condition,
                      float(np.sqrt(np.mean((x @ coef - y) ** 2))),
                      canonical_hash([e.to_dict() for e in training]))


def select_frame(model, evidence):
    """Compare two preregistered rotations after fitting a nuisance intercept.

    Constant commanded inputs cannot distinguish these frame hypotheses with
    a free intercept. Ties use FRAME_A. This is a numerical baseline; residual
    rank or a preferred hypothesis provides no probability guarantee.
    """
    if type(model) is not NominalARX:
        raise ValueError("requires a frozen nominal ARX model")
    a, b, c = np.asarray(model.inertia), np.asarray(model.response), np.asarray(model.intercept)
    if a.shape != (2, 2) or b.shape != (2, 2) or c.shape != (2,) or not all(np.isfinite(v).all() for v in (a, b, c)):
        raise ValueError("invalid nominal ARX coefficients")
    if np.linalg.svd(b, compute_uv=False)[-1] < 1e-8:
        raise ValueError("noninvertible nominal response")
    previous, commands, observed = _design(evidence)
    scores, offsets = [], []
    for rotation in ROTATIONS:
        residual = observed - previous @ a.T - commands @ rotation.T @ b.T - c
        mean = np.mean(residual, axis=0)
        offsets.append(np.linalg.solve(b, mean).tolist())
        scores.append(float(np.mean((residual - mean) ** 2)))
    informative = bool(np.max(np.abs(commands - np.mean(commands, axis=0))) > 1e-8)
    tie = abs(scores[0] - scores[1]) <= 1e-12
    index = 0 if not informative or tie else int(np.argmin(scores))
    return {"controller_id": ("FRAME_A", "FRAME_B")[index], "valid": True,
            "informative_input": informative, "numerical_tie": tie,
            "residual_mse": scores, "nuisance_offsets": offsets,
            "reason": "CONSTANT_INPUT_ALIAS" if not informative else "NUMERICAL_TIE" if tie else "MINIMUM_RESIDUAL",
            "samples": len(observed), "confidence_certificate": False}


def registered_controller(controller_id):
    if controller_id == "FRAME_A":
        matrix, offset = np.eye(2), [.1, -.1, 0., 0.]
    elif controller_id == "FRAME_B":
        matrix, offset = ROTATIONS[1].T, [.1, .1, 0., 0.]
    elif controller_id == "UNCORRECTED":
        matrix, offset = np.eye(2), [0., 0., 0., 0.]
    else:
        raise ValueError("unknown registered controller")
    return {"id": controller_id, "matrix_xy": matrix.tolist(), "offset": offset}


def encode_command(controller, raw_policy):
    """Common bounded policy/command interface for every method in this version."""
    if type(controller) is not dict or set(controller) != {"id", "matrix_xy", "offset"}:
        raise ValueError("invalid controller schema")
    if controller["id"] in ("FRAME_A", "FRAME_B", "UNCORRECTED"):
        if controller != registered_controller(controller["id"]):
            raise ValueError("registered controller was changed")
    elif controller["id"] in ("LEGACY_AFFINE", "LEGACY_NEAREST"):
        offset = np.asarray(controller["offset"], dtype=float)
        if controller["matrix_xy"] != np.eye(2).tolist() or offset.shape != (4,) or not np.isfinite(offset).all() or \
                np.any(np.abs(offset) > .200001) or np.any(offset[2:] != 0):
            raise ValueError("legacy controller is not a bounded xy translation")
    else:
        raise ValueError("unknown registered controller")
    desired = np.asarray(raw_policy, dtype=np.float32)
    if desired.shape != (4,) or not np.isfinite(desired).all():
        raise ValueError("invalid fixed-policy action")
    desired = np.clip(desired, -1, 1)
    command = desired.copy()
    command[:2] = np.asarray(controller["matrix_xy"], dtype=np.float32) @ desired[:2]
    command += np.asarray(controller["offset"], dtype=np.float32)
    return np.clip(command, -1, 1).astype(np.float32)
