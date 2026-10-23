"""Standard calibrated trajectory response, fitted only to known commands.

This is an affine identification baseline, not an uncertainty certificate.
"""
from dataclasses import dataclass,asdict
import hashlib
import json
import numpy as np
from src.probe.continuous import ContinuousEvidence,symmetric_program


def trajectory_features(evidence: ContinuousEvidence):
    if type(evidence) is not ContinuousEvidence or evidence.steps!=16 or evidence.stop_reason!="PROGRAM_COMPLETE":
        raise ValueError("requires a complete continuous 16-step probe")
    rows=evidence.transitions
    if rows[-1].after!=evidence.final.observation:
        raise ValueError("final observation mismatch")
    initial=np.array(rows[0].before[:2],dtype=float)
    previous=rows[0].before
    values=[]
    for row in rows:
        if row.before!=previous or len(row.after)<3 or len(row.command)!=4:
            raise ValueError("discontinuous probe trajectory")
        values.extend(np.array(row.after[:2],dtype=float)-initial)
        previous=row.after
    vector=np.asarray(values,dtype=float)
    if not np.isfinite(vector).all(): raise ValueError("nonfinite probe feature")
    return vector


def known_offset_program(offset):
    offset=np.asarray(offset,dtype=np.float32)
    if offset.shape!=(2,) or not np.isfinite(offset).all() or np.any(np.abs(offset)>.2):
        raise ValueError("known command offsets must be bounded xy values")
    addition=np.array([*offset,0.,0.],dtype=np.float32)
    return tuple(tuple(float(x) for x in np.array(command,dtype=np.float32)+addition) for command in symmetric_program())


@dataclass(frozen=True)
class ResponseModel:
    nominal: tuple[float,...]
    sensitivity: tuple[tuple[float,float],...]
    command_offsets: tuple[tuple[float,float],...]
    centroids: tuple[tuple[float,...],...]
    training_trials: int
    training_digest: str

    def to_dict(self): return asdict(self)


def fit_response(training):
    """training = sequence of (known xy command offset, visible probe evidence)."""
    if not training: raise ValueError("empty training population")
    offsets=[]; features=[]
    for offset,evidence in training:
        expected=known_offset_program(offset)
        if tuple(row.command for row in evidence.transitions)!=expected:
            raise ValueError("known commanded offset does not match collected actions")
        offsets.append(tuple(float(x) for x in offset))
        features.append(trajectory_features(evidence))
    x=np.column_stack((np.ones(len(offsets)),offsets)); y=np.asarray(features)
    if np.linalg.matrix_rank(x)!=3: raise ValueError("calibration commands lack full planar rank")
    coef=np.linalg.lstsq(x,y,rcond=None)[0]
    response=coef[1:].T
    singular=np.linalg.svd(response,compute_uv=False)
    if singular[-1]<1e-6 or singular[0]/singular[-1]>1e6:
        raise ValueError("calibrated response is unidentifiable")
    labels=sorted(set(offsets))
    centroids=[np.mean([f for label,f in zip(offsets,features) if label==key],axis=0) for key in labels]
    digest=hashlib.sha256(json.dumps({"offsets":offsets,"features":y.tolist()},sort_keys=True).encode()).hexdigest()
    return ResponseModel(tuple(coef[0]),tuple(tuple(r) for r in response),tuple(labels),
                         tuple(tuple(row) for row in centroids),len(training),digest)


def infer_offset(model,evidence,*,method="affine"):
    """Inference sees only model and nominal-program observations, not labels."""
    if tuple(row.command for row in evidence.transitions)!=symmetric_program():
        raise ValueError("deployment estimator requires the nominal command program")
    return infer_features(model,trajectory_features(evidence),method=method)


def infer_features(model,features,*,method="affine"):
    """Calibration qualification uses features with command labels held outside."""
    vector=np.asarray(features,dtype=float)
    if vector.shape!=(32,) or not np.isfinite(vector).all(): raise ValueError("invalid visible feature vector")
    if method=="affine":
        estimate=np.linalg.lstsq(np.array(model.sensitivity),vector-np.array(model.nominal),rcond=None)[0]
    elif method=="nearest":
        distance=np.linalg.norm(np.array(model.centroids)-vector,axis=1)
        estimate=np.array(model.command_offsets[int(np.argmin(distance))])
    else: raise ValueError("unknown calibrated baseline")
    return tuple(float(x) for x in estimate)
