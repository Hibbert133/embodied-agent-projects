"""Evaluation-only identity, not a physical-noise or causal attribution model."""
import numpy as np
from src.probe import correction_scope_model_v1 as public


def terms(row):
    public.public_state(row['before']);public.public_state(row['after'])
    u=np.asarray(row['command'],float)
    if u.shape!=(4,) or not np.isfinite(u).all() or np.max(abs(u))>1:raise ValueError('actual bounded sent command required')
    b=np.asarray(row['before']['observation']);a=np.asarray(row['after']['observation']);d=(a[:2]-b[:2])/.01
    command=float(u[:2]@u[:2]);motion=float(d@d);alignment=float(2*(u[:2]@d));error=float(np.sum((d-u[:2])**2))
    bin_index=int(np.argmax(public.query_vector(row)[0]))
    return dict(command_xy=u[:2].tolist(),observed_scaled_delta_xy=d.tolist(),bin_index=bin_index,
        error=error,command_energy=command,motion_energy=motion,alignment=alignment,identity_gap=error-(command+motion-alignment))


def window(rows):
    if not rows:return dict(n=0,missing_reason='NO_EXECUTED_WINDOW',means=None,joint=None,command_only_relative_l2=None)
    values=[terms(r) for r in rows];keys=('error','command_energy','motion_energy','alignment')
    means={k:float(np.mean([v[k] for v in values])) for k in keys};joint={k:np.zeros(24) for k in keys};p=np.zeros(24)
    for value in values:
        p[value['bin_index']]+=1
        for k in keys:joint[k][value['bin_index']]+=value[k]
    joint={k:(v/len(values)).tolist() for k,v in joint.items()};e=np.asarray([v['error'] for v in values]);u=np.asarray([v['command_energy'] for v in values])
    return dict(n=len(rows),missing_reason=None,means=means,joint=joint,occupancy=(p/len(values)).tolist(),
        command_only_relative_l2=None if np.linalg.norm(e)==0 else float(np.linalg.norm(e-u)/np.linalg.norm(e)),
        command_only_absolute_l2=float(np.linalg.norm(e-u)/np.sqrt(len(e))),
        max_identity_gap=float(max(abs(v['identity_gap']) for v in values)))
