"""Independent scalar-array reconstruction of saved LINEAR_ARX movement fits.

No calls to production sample construction, features, forward problem or inverse
fitter. Uses the same declared solver/settings; reports audit solver work apart
from the saved production counter. This is arithmetic audit, not model validity.
"""
import hashlib
import json
import math

import numpy as np
from scipy.optimize import least_squares


def require(ok, message):
    if not ok:raise ValueError(message)


def close(actual, expected):
    require(np.shape(actual) == np.shape(expected) and np.allclose(actual, expected, atol=2e-8, rtol=2e-7),
            "independent movement-fit arithmetic differs")


def check_fit(model, history, estimate):
    sha = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    context = history["context"];rows = history["transitions"]
    require(estimate["history_sha256"] == sha(history) and estimate["model_sha256"] == sha(model)
            and estimate["decision_step"] == history["decision_step"] and estimate["movement_responses"] == len(rows)
            and estimate["fit_attempts"] == 1 and estimate["physical_response_qualified"] is False
            and estimate["task_utility_demonstrated"] is False and estimate["probability_guarantee"] is False,
            "numerical source, cutoff or claim differs")
    observations = [v["observation"] for v in context]
    x, z, y, samples = [], [], [], []
    for i, row in enumerate(rows):
        require(row["completed_step"] == history["start_step"]+i+1
                and row["before"]["observation"] == observations[-1], "noncausal numerical history")
        before = np.array(observations[-1]);command = list(row["command"])
        last = before[:3]-np.array(observations[-2])[:3]
        prior = np.array(observations[-2])[:3]-np.array(observations[-3])[:3]
        after = row["after"]["observation"];target = np.array(after)[:2]-before[:2]
        z.append([*last, *prior, *command]);x.append([*command[:2], 1.]);y.append(target)
        samples.append({"step": row["completed_step"], "query": {"observation": observations[-1],
            "last_displacement": last.tolist(), "prior_displacement": prior.tolist(), "command": command}, "displacement": target.tolist()})
        observations.append(after)
    fit = estimate["fit"]
    require(estimate["status"] == ("VALID_WORKING_ESTIMATE" if fit["valid"] else "INVALID_ESTIMATE"), "numeric status differs")
    require(fit["samples"] == len(rows), "fit discarded movement responses")
    sample_hash = hashlib.sha256(json.dumps(samples, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    require(sample_hash == fit["sample_digest"], "independent sample reconstruction differs")
    if len(rows) < 6:
        require(fit["valid"] is False and fit["reason"] == "INSUFFICIENT_SAMPLES" and estimate["optimizer_nfev"] == 0, "short-input rejection differs")
        return {"audit_nfev": 0, "responses": len(rows), "valid": False}
    x, z, y = np.array(x), np.array(z), np.array(y)
    rank = int(np.linalg.matrix_rank(x));norm = np.sqrt(np.mean(x*x, axis=0))
    condition = float(np.linalg.cond(x/np.where(norm > 1e-12, norm, 1.)))
    require(fit["design_rank"] == rank, "input rank differs")
    if math.isfinite(condition):close(fit["scaled_condition"], condition)
    else:require(fit["scaled_condition"] is None, "nonfinite condition must remain null")
    if rank != 3 or not math.isfinite(condition) or condition > 1e6:
        require(fit["valid"] is False and fit["reason"] == "MISSING_OR_ILL_CONDITIONED_INPUT_SUPPORT"
                and estimate["optimizer_nfev"] == 0, "input-support rejection differs")
        return {"audit_nfev": 0, "responses": len(rows), "valid": False}
    beta = np.asarray(model["coefficients"]);mean = np.array(model["mean"]);scale = np.array(model["scale"])
    response = beta[7:9].T/scale[6:8]
    def prediction(p):
        inputs = z.copy();inputs[:,6:8] = np.clip(x@np.array(p).reshape(2,3).T, -1., 1.)
        # Build predictions output by output, separately from production feature/predict functions.
        standardized = (inputs-mean)/scale
        return np.column_stack([beta[0,j]+sum(standardized[:,k]*beta[k+1,j] for k in range(10)) for j in range(2)])
    def residual(p):return ((prediction(p)-y)/.001).ravel()
    def jacobian(p):
        effective = x@np.array(p).reshape(2,3).T;out = np.zeros((2*len(rows),6))
        for i in range(len(rows)):
            for j in range(2):
                for axis in range(2):
                    if -1 < effective[i,axis] < 1:
                        out[2*i+j,3*axis:3*axis+3] = response[j,axis]*x[i]/.001
        return out
    lower = np.array([-2.,-2.,-.3,-2.,-2.,-.3]);upper = -lower
    if np.linalg.svd(response, compute_uv=False)[-1] < 1e-8:initial = np.array([1.,0.,0.,0.,1.,0.])
    else:
        coefficient = np.linalg.lstsq(x, y-prediction(np.zeros(6)), rcond=None)[0]
        initial = np.linalg.solve(response, coefficient.T).ravel()
    solved = least_squares(residual, np.clip(initial,lower+1e-9,upper-1e-9), jac=jacobian, bounds=(lower,upper),
        method="trf", ftol=1e-8, xtol=1e-8, gtol=1e-8, x_scale=1., loss="linear", max_nfev=64)
    candidates = [("CLOSED_LINEAR", initial, bool(np.all(np.abs(x@initial.reshape(2,3).T) <= 1)), 0),
                  ("BOUNDED_LINEAR_REFINEMENT", solved.x, bool(solved.success), int(solved.nfev))]
    require(len(fit["optimizer_trials"]) == 2, "two registered linear trials required")
    usable = []
    for saved, (name, parameters, success, calls) in zip(fit["optimizer_trials"], candidates):
        require(saved["start"] == name and type(saved["nfev"]) is int and 0 <= saved["nfev"] <= 64, "trial identity/cost differs")
        if name == "CLOSED_LINEAR":require(saved["nfev"] == 0, "closed solve cost differs")
        close(saved["parameters"], parameters)
        require(saved["success"] == success, "solver acceptance differs")
        error = float(np.sqrt(np.mean((prediction(parameters)-y)**2)))
        close(saved["residual_rmse_m"], error)
        if success and np.all(parameters >= lower-1e-12) and np.all(parameters <= upper+1e-12):usable.append((error,name,parameters))
    require(estimate["optimizer_nfev"] == sum(t["nfev"] for t in fit["optimizer_trials"]), "saved optimization total differs")
    if not usable:
        require(fit["valid"] is False and fit["reason"] == "OPTIMIZER_OR_PARAMETER_DOMAIN_FAILURE", "parameter rejection differs")
    else:
        error, name, p = min(usable, key=lambda item:item[0]);matrix = p.reshape(2,3)
        close(fit["matrix_xy"], matrix[:,:2]);close(fit["bias_xy"], matrix[:,2]);close(fit["residual_rmse_m"], error)
        singular = np.linalg.svd(matrix[:,:2], compute_uv=False);close(fit["singular_values"], singular)
        valid = bool(singular[-1] >= .25 and singular[0] <= 4)
        require(fit["valid"] == valid and fit["reason"] == ("POINT_FORWARD_PREDICTION_ERROR_FIT" if valid else "UNSTABLE_ESTIMATED_INVERSE"), "inverse acceptance differs")
        # Tied trials may swap under independent floating-point arithmetic.
        selected = next(t for t in fit["optimizer_trials"] if t["start"] == fit["selected_start"])
        close(selected["residual_rmse_m"], error)
    return {"audit_nfev": int(solved.nfev), "responses": len(rows), "valid": fit["valid"]}
