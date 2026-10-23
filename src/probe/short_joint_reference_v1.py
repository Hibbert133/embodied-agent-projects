"""Draft standard four-step marginal estimator; no physical qualification.

This independent reference does not change the frozen eight-step interface or
select a probe program. Inputs are observed ColdPrefix data and the declared
nominal response model, never actuator truth, simulator state or future data.
"""
import numpy as np
from scipy.optimize import least_squares
from src.probe.cold_start_response import ColdPrefix,validate_model,clipped_normal_mean,SCOPE


def infer_four(saved,prefix):
    offset,impulse,covariance=validate_model(saved)
    if type(prefix) is not ColdPrefix or prefix.task!=saved['task']:
        raise ValueError('matching observed cold prefix and task-specific nominal model required')
    result={'valid':False,'model':'JOINT_FOUR_STEP_REFERENCE_V1','source_model_scope':SCOPE,
        'scope':'FOUR_STEP_MARGINAL_SOFTWARE_REFERENCE','physical_response_qualified':False,'probability_guarantee':False,
        'nfev':0,'observed_prefix_steps':len(prefix.commands),'observed_rows_used':0,'working_covariance':None}
    if len(prefix.commands)!=4:return {**result,'reason':'EXACT_FOUR_STEP_PREFIX_REQUIRED'}
    initial=np.asarray(prefix.initial_observation)
    if (np.any(initial[:3]<saved['initial_hand_lower']) or np.any(initial[:3]>saved['initial_hand_upper']) or
        np.linalg.norm(initial[4:7]-initial[:3])<saved['minimum_initial_object_distance']):
        return {**result,'reason':'OUTSIDE_CONTROLLED_RESET_SCOPE'}
    x=np.c_[np.asarray(prefix.commands)[:,:2],np.ones(4)]
    result['input_design_rank']=int(np.linalg.matrix_rank(x))
    if result['input_design_rank']!=3:return {**result,'reason':'MISSING_INPUT_SUPPORT'}
    # Marginalize future responses by taking the covariance block, never the
    # corresponding block of the full precision/conditional covariance.
    offset=offset[:8];impulse=impulse[:8,:8];chol=np.linalg.cholesky(covariance[:8,:8])
    observed=prefix.displacements.ravel()
    linear=np.column_stack([impulse@(x@np.eye(6)[i].reshape(2,3).T).ravel() for i in range(6)])
    whitened=np.linalg.solve(chol,linear);result['whitened_design_rank']=int(np.linalg.matrix_rank(whitened))
    if result['whitened_design_rank']!=6:return {**result,'reason':'MARGINAL_RESPONSE_UNIDENTIFIABLE'}
    start=np.linalg.lstsq(whitened,np.linalg.solve(chol,observed-offset),rcond=None)[0]
    lower=np.array([-2.,-2.,-.3,-2.,-2.,-.3]);upper=-lower

    def predict(parameters):
        mean,_=clipped_normal_mean(x@parameters.reshape(2,3).T)
        return offset+impulse@mean.ravel()

    def jacobian(parameters):
        _,slope=clipped_normal_mean(x@parameters.reshape(2,3).T)
        jac=np.column_stack([impulse@((x@np.eye(6)[i].reshape(2,3).T)*slope).ravel() for i in range(6)])
        return np.linalg.solve(chol,jac)

    def residual(parameters):return np.linalg.solve(chol,predict(parameters)-observed)

    fitted=least_squares(residual,np.clip(start,lower+1e-9,upper-1e-9),jac=jacobian,
        bounds=(lower,upper),ftol=1e-8,xtol=1e-8,gtol=1e-8,max_nfev=64)
    matrix=fitted.x.reshape(2,3);singular=np.linalg.svd(matrix[:,:2],compute_uv=False);jac=jacobian(fitted.x)
    result.update(matrix_xy=matrix[:,:2].tolist(),bias_xy=matrix[:,2].tolist(),nfev=int(fitted.nfev),observed_rows_used=4,
        residual_rmse_m=float(np.sqrt(np.mean((predict(fitted.x)-observed)**2))),
        fitted_jacobian_rank=int(np.linalg.matrix_rank(jac)))
    if not(fitted.success and singular[-1]>=.25 and singular[0]<=4 and result['fitted_jacobian_rank']==6):
        return {**result,'reason':'OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE'}
    try:
        working=np.linalg.solve(jac.T@jac,np.eye(6));working=(working+working.T)/2
        if not np.isfinite(working).all():raise ValueError('nonfinite working covariance')
        np.linalg.cholesky(working)
    except (ValueError,np.linalg.LinAlgError):return {**result,'reason':'WORKING_INFORMATION_NOT_POSITIVE_DEFINITE'}
    return {**result,'valid':True,'reason':'WORKING_FOUR_STEP_MARGINAL_FIT','working_covariance':working.tolist()}
