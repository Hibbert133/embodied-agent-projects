"""Frozen standard estimators for the continuous-probe development study."""
from dataclasses import asdict
import numpy as np
from src.probe.continuous import fit_local_response
from src.planar_recovery import estimate_planar_correction
from src.recovery_agent import DEFAULT_CORRECTION_MAGNITUDES

METHODS = ("NO_PROBE", "CONT_NO_CORRECTION", "CONT_STATIC", "CONT_DYNAMIC", "RESET_REFERENCE")


def static_fit(evidence):
    rows = evidence.transitions
    if len(rows) < 8:
        return {"valid": False, "reason": "INSUFFICIENT_TRANSITIONS", "bias_in_command_units": None}
    x = np.array([[*r.command[:2],1.] for r in rows])
    y = np.array([np.array(r.after[:2])-r.before[:2] for r in rows])
    if np.linalg.matrix_rank(x) != 3:
        return {"valid": False, "reason": "UNIDENTIFIABLE_DESIGN", "bias_in_command_units": None}
    coef = np.linalg.lstsq(x,y,rcond=None)[0]
    b, c = coef[:2].T,coef[2]
    singular = np.linalg.svd(b,compute_uv=False)
    if singular[-1] < 1e-6 or singular[0]/singular[-1] > 1e6:
        return {"valid": False, "reason": "UNIDENTIFIABLE_RESPONSE", "bias_in_command_units": None}
    return {"valid": True, "reason": "STATIC_OLS_ESTIMATE_ONLY", "bias_in_command_units": np.linalg.solve(b,c).tolist(),
            "response": b.tolist(), "intercept": c.tolist(), "residual_rmse": float(np.sqrt(np.mean((x@coef-y)**2)))}


def decision(method, evidence=None, reset_inference=None):
    if method not in METHODS:
        raise ValueError("unknown continuous baseline")
    if method in ("NO_PROBE","CONT_NO_CORRECTION"):
        return {"correction": [0.,0.,0.,0.], "fit": None}
    if method == "RESET_REFERENCE":
        gain = np.array(reset_inference["axis_response_gain"])
        valid = bool(np.all(np.isfinite(gain)) and np.all(np.abs(gain) >= 1e-6))
        fit = {"valid":valid,"reason":"RESET_SYMMETRIC_REFERENCE", "bias_in_command_units":
               (np.array(reset_inference["estimated_drift_per_step"])/gain).tolist() if valid else None}
    else:
        fit = static_fit(evidence) if method == "CONT_STATIC" else asdict(fit_local_response(evidence))
    bias = fit["bias_in_command_units"]
    if not fit["valid"] or bias is None or not np.isfinite(bias).all():
        return {"correction": [0.,0.,0.,0.], "fit":fit}
    estimate = estimate_planar_correction({"inference":{"estimated_drift_per_step":bias,
        "axis_response_gain":[1.,1.],"residual":0.}}, allowed_magnitudes=DEFAULT_CORRECTION_MAGNITUDES)
    return {"correction": list(estimate.simultaneous_correction),"fit":fit}
