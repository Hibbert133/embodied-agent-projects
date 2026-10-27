"""Observed symmetry decomposition, not a new predictor or a model fit."""
import numpy as np
from src.analysis.response_qualification_io_v1 import require


def vector(value,size=2):
    x=np.asarray(value,float);require(x.shape==(size,) and np.isfinite(x).all(),'finite measured vector');return x


def response(zero,plus,minus,native_zero,native_plus,native_minus):
    z,p,m=(vector(v) for v in (zero,plus,minus));nz,np_,nm=(vector(v) for v in (native_zero,native_plus,native_minus))
    even=(p+m)/2-z;odd=(p-m)/2;native_even=(np_+nm)/2-nz;tracking_even=even-native_even
    floor=float(even@even/3);native_term=float(native_even@native_even/3);tracking_term=float(tracking_even@tracking_even/3);cross=float(2*(native_even@tracking_even)/3)
    return dict(observed_even_xy_m=even.tolist(),observed_odd_xy_m=odd.tolist(),native_even_xy_m=native_even.tolist(),tracking_even_xy_m=tracking_even.tolist(),
        linear_command_class_floor_m2=floor,native_even_term_m2=native_term,tracking_even_term_m2=tracking_term,native_tracking_cross_m2=cross,
        even_decomposition_error_m2=float(floor-native_term-tracking_term-cross))


def saved_error(zero,plus,minus,predictions):
    z,p,m=(vector(v) for v in (zero,plus,minus));pred=np.asarray(predictions,float);require(pred.shape==(3,2) and np.isfinite(pred).all(),'three saved directed pair forecasts')
    actual=np.stack((p-z,m-z,m-p));even=(p+m)/2-z;odd=(p-m)/2
    projected=(pred[0]-pred[1]-2*pred[2])/6
    defect=pred-np.stack((projected,-projected,-2*projected))
    mse=float(np.sum((pred-actual)**2)/6);odd_error=float(np.sum((projected-odd)**2));floor=float(even@even/3)
    numerical_term=float((np.sum(defect**2)-2*even@(defect[0]+defect[1]))/6)
    return dict(saved_pair_mse_m2=mse,linear_command_class_floor_m2=floor,saved_odd_component_error_m2=odd_error,saved_nonclass_correction_m2=numerical_term,
        saved_class_defect_l2_m=float(np.linalg.norm(defect)),decomposition_error_m2=float(mse-floor-odd_error-numerical_term))


def actuator_parity(applied,actuator_clips,workspace_clips):
    x=np.asarray(applied,float);require(x.ndim==3 and x.shape[0]==3 and x.shape[2]==4 and 1<=x.shape[1]<=16 and np.isfinite(x).all(),'three actual input histories')
    e=(x[1,:,:3]+x[2,:,:3])/2-x[0,:,:3]
    return dict(applied_even_max_abs_xyz_command=float(np.max(abs(e))),applied_even_l2_xyz_command=float(np.linalg.norm(e)),
        applied_even_nonzero_scalars=int(np.count_nonzero(e)),actuator_final_clip_axes=int(sum(actuator_clips)),native_workspace_clip_axes=int(sum(workspace_clips)))
