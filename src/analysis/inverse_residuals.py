"""Oracle-only accounting of an already saved inverse fit's parameter error.

This is a numerical diagnosis under the frozen LINEAR_ARX predictor, not a new
estimator, physical error attribution, confidence certificate or causal test.
It requires recorded executed inputs and private actuator truth unavailable to
the Agent, and never constructs or returns an executable controller.
"""
from dataclasses import dataclass
import numpy as np

from src.probe.forward_prediction import features, vector
from src.probe.operator_identification import ForwardOperatorProblem, OperatorSample

SCOPE="EVALUATOR_ONLY_SAVED_INVERSE_ERROR_ACCOUNTING"
PARAMETER_SCALE=np.array((1.,1.,.3,1.,1.,.3))
COMPONENTS=("applied_input_prediction_residual","propagated_input_noise","host_rounding",
            "fit_residual_adjustment","secant_nullspace")


def array(value,shape):
    result=np.asarray(value,float)
    if result.shape!=shape or not np.isfinite(result).all(): raise ValueError("finite oracle diagnostic shape required")
    return result


@dataclass(frozen=True)
class OracleActuation:
    matrix_xy: tuple
    bias_xy: tuple

    def __post_init__(self):
        matrix=array(self.matrix_xy,(2,2)); bias=array(self.bias_xy,(2,))
        if np.any(np.abs(matrix)>2) or np.any(np.abs(bias)>.3): raise ValueError("registered evaluator actuator domain required")
        object.__setattr__(self,"matrix_xy",tuple(tuple(row) for row in matrix.tolist()))
        object.__setattr__(self,"bias_xy",tuple(bias.tolist()))

    @property
    def host_parameters(self):
        return np.column_stack((np.asarray(self.matrix_xy,np.float32),np.asarray(self.bias_xy,np.float32))).astype(float).ravel()

    def noiseless_host_action(self,sent):
        sent=np.asarray(vector(sent,4),np.float32).copy()
        sent[:2]=np.asarray(self.matrix_xy,np.float32)@sent[:2]+np.asarray(self.bias_xy,np.float32)
        return np.clip(sent,-1,1).astype(float)


def command_prediction(problem,sample,actual_command):
    command=array(actual_command,(4,))
    if np.any(np.abs(command)>1): raise ValueError("recorded executed action outside command box")
    values=np.asarray(features(sample.query,"LINEAR_ARX"),float).copy(); values[6:10]=command
    return problem.constant+problem.linear@((values-problem.mean)/problem.scale)


def decompose_oracle_prefix(model,samples,executed_actions,oracle,saved_parameters):
    if type(oracle) is not OracleActuation or model.get("method")!="LINEAR_ARX" or not samples or any(type(s) is not OperatorSample for s in samples):
        raise ValueError("explicit oracle-only block and frozen linear reference required")
    if any(a.step>=b.step for a,b in zip(samples,samples[1:])): raise ValueError("chronological completed source samples required")
    actual=array(executed_actions,(len(samples),4)); saved=np.asarray(vector(saved_parameters,6))
    if np.any(np.abs(saved)>np.array((2.,2.,.3,2.,2.,.3))+1e-8): raise ValueError("saved parameters outside registered fit domain")
    sent=np.asarray([s.query.command for s in samples])
    if np.any(np.abs(actual)>1) or not np.array_equal(actual[:,3],sent[:,3]): raise ValueError("invalid recorded action or altered gripper")
    problem=ForwardOperatorProblem(model,tuple(samples)); truth=oracle.host_parameters
    predicted_truth=problem.predictions(truth); predicted_saved=problem.predictions(saved)
    mean_actions=np.asarray([oracle.noiseless_host_action(s.query.command) for s in samples])
    predicted_actual=np.asarray([command_prediction(problem,s,a) for s,a in zip(samples,actual)])
    predicted_mean=np.asarray([command_prediction(problem,s,a) for s,a in zip(samples,mean_actions)])
    residuals={"applied_input_prediction_residual":problem.targets-predicted_actual,
               "propagated_input_noise":predicted_actual-predicted_mean,
               "host_rounding":predicted_mean-predicted_truth}
    total=problem.targets-predicted_truth; reconstructed=sum(residuals.values())
    residual_error=float(np.max(np.abs(total-reconstructed)))
    if residual_error>1e-12: raise ValueError("exact prediction-residual accounting failed")
    true_raw=problem.x@truth.reshape(2,3).T; saved_raw=problem.x@saved.reshape(2,3).T
    difference=saved_raw-true_raw
    weights=np.divide(np.clip(saved_raw,-1,1)-np.clip(true_raw,-1,1),difference,
                      out=((true_raw>-1)&(true_raw<1)).astype(float),where=difference!=0)
    response=problem.linear[:,problem.indices]/problem.scale[list(problem.indices)]
    weighted=response[None,:,:]*weights[:,None,:]
    secant=np.concatenate((weighted[:,:,0,None]*problem.x[:,None,:],weighted[:,:,1,None]*problem.x[:,None,:]),axis=2).reshape(-1,6)
    delta=saved-truth
    secant_error=float(np.max(np.abs(secant@delta-(predicted_saved-predicted_truth).ravel())))
    if secant_error>1e-12: raise ValueError("finite-change clipped-model identity failed")
    inverse=np.linalg.pinv(secant,rcond=1e-10)
    projection={name:inverse@value.ravel() for name,value in residuals.items()}
    projection["fit_residual_adjustment"]=-inverse@(problem.targets-predicted_saved).ravel()
    projection["secant_nullspace"]=(np.eye(6)-inverse@secant)@delta
    parameter_error=float(np.max(np.abs(sum(projection.values())-delta)))
    if parameter_error>1e-8: raise ValueError("saved-parameter accounting identity failed")
    scaled=delta/PARAMETER_SCALE; norm=float(np.linalg.norm(scaled))
    contributions={name:float(scaled@(value/PARAMETER_SCALE)/norm) if norm else 0. for name,value in projection.items()}
    if abs(sum(contributions.values())-norm)>1e-8: raise ValueError("signed directional accounting failed")
    squared={name:float(np.mean(value*value)) for name,value in residuals.items()}
    names=tuple(residuals); cross={f"{names[i]}__{names[j]}":float(2*np.mean(residuals[names[i]]*residuals[names[j]]))
                                  for i in range(3) for j in range(i+1,3)}
    mse=float(np.mean(total*total))
    if abs(sum(squared.values())+sum(cross.values())-mse)>1e-12: raise ValueError("squared-error cross-term accounting failed")
    phase_scores={}
    for name,mask in (("PROBE",np.array([s.step<=8 for s in samples])),("POLICY",np.array([s.step>8 for s in samples]))):
        if mask.any():
            phase_scores[name]={"samples":int(mask.sum()),"total_rmse_m":float(np.sqrt(np.mean(total[mask]**2))),
                                 **{key+"_rmse_m":float(np.sqrt(np.mean(value[mask]**2))) for key,value in residuals.items()}}
    singular=np.linalg.svd(secant,compute_uv=False); rank=int(np.sum(singular>1e-10*singular[0])) if singular[0]>0 else 0
    return {"scope":SCOPE,"samples":len(samples),"oracle_host_parameters":truth.tolist(),"saved_parameters":saved.tolist(),
            "parameter_error":delta.tolist(),"gain_error_frobenius":float(np.linalg.norm(delta.reshape(2,3)[:,:2])),
            "bias_error_norm":float(np.linalg.norm(delta.reshape(2,3)[:,2])),"scaled_parameter_error_norm":norm,
            "residual_rmse_m":float(np.sqrt(mse)),"component_mse":squared,"cross_mse":cross,"phase_scores":phase_scores,
            "parameter_components":{name:value.tolist() for name,value in projection.items()},"signed_scaled_error_contributions":contributions,
            "secant_rank":rank,"true_noiseless_xy_clipped_samples":int(np.any(np.abs(true_raw)>=1,axis=1).sum()),
            "saved_noiseless_xy_clipped_samples":int(np.any(np.abs(saved_raw)>=1,axis=1).sum()),
            "actual_xy_boundary_samples":int(np.any(np.abs(actual[:,:2])==1,axis=1).sum()),
            "saved_parameter_bound_active":bool(np.any(np.abs(saved)>=np.array((2.,2.,.3,2.,2.,.3))-1e-8)),
            "identity_errors":{"residual_max_abs":residual_error,"secant_max_abs":secant_error,"parameter_max_abs":parameter_error},
            "controller_returned":False,"physical_response_qualified":False,"probability_guarantee":False}
