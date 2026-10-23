"""Finite-source, fresh-future contrasts; standard variance identities, not novelty."""
import numpy as np

ARMS=("REUSE_OLD","PROBE_KEEP","PROBE_UPDATE","PROBE_UPDATE_KEEP")
CONTRASTS=("total_keep","motion_budget","update_keep","total_strict","fallback")


def contrasts(losses):
    value=np.asarray(losses,float)
    if value.ndim!=2 or value.shape[1]!=4 or value.shape[0]<2 or not np.isfinite(value).all() or np.any(value<0) or np.any(value>500):
        raise ValueError("at least two fresh futures, four registered arms and bounded losses required")
    r,p,u,k=value.T
    result=np.column_stack((r-k,r-p,p-k,r-u,u-k))
    if not np.array_equal(result[:,0],result[:,1]+result[:,2]):raise ValueError("pathwise decomposition differs")
    return result


def nested_summary(loss_matrices):
    arrays=[contrasts(v) for v in loss_matrices]
    if len(arrays)<2 or len({a.shape for a in arrays})!=1:raise ValueError("at least two contexts with same fresh-future allocation required")
    values=np.stack(arrays);n,j,d=values.shape
    means=values.mean(axis=1)
    within=np.stack([np.cov(a,rowvar=False,ddof=1) for a in values])
    observed=np.cov(means,rowvar=False,ddof=1)
    mc_mean_covariance=within.mean(axis=0)/j
    corrected=observed-mc_mean_covariance
    # No PSD clipping: negative estimated finite-source variances remain visible.
    return {"contexts":n,"fresh_futures_per_context":j,"contrast_order":list(CONTRASTS),
        "mean_contrast":means.mean(axis=0).tolist(),"context_mean_contrasts":means.tolist(),
        "within_future_covariance_mean":within.mean(axis=0).tolist(),"observed_context_mean_covariance":observed.tolist(),
        "mc_mean_noise_covariance":mc_mean_covariance.tolist(),"noise_corrected_finite_source_covariance":corrected.tolist(),
        "per_context_mc_standard_error":np.sqrt(np.diagonal(within,axis1=1,axis2=2)/j).tolist(),
        "per_context_both_strict_signs_observed":((values.min(axis=1)<0)&(values.max(axis=1)>0)).tolist(),
        "scope":"Conditional on fixed realized source contexts, fresh evaluator futures independent of source behavior. Noise correction is a standard finite-source identity, not visible-evidence calibration, sign certification or an online method."}


def stream_bootstrap(loss_matrices,context_streams,stream_strata,*,samples=10000,seed=20261021):
    """State-weighted ratio with whole-stream resampling, including empty streams.

    Stratification keys are sorted (family, schedule). Within each key source
    stream IDs are sorted. Undefined draws are counted, never silently omitted.
    """
    if len(loss_matrices)!=len(context_streams) or not loss_matrices:
        raise ValueError('nonempty aligned context ownership required')
    if type(samples) is not int or samples<1 or type(seed) is not int:
        raise ValueError('integer bootstrap allocation required')
    ids=sorted(stream_strata)
    if any(type(k) is not int for k in ids) or any(k not in stream_strata for k in context_streams):
        raise ValueError('all source streams, including empty ones, required')
    keys=sorted(set(tuple(v) for v in stream_strata.values()))
    if any(len(v)!=2 or any(type(x) is not str for x in v) for v in stream_strata.values()):
        raise ValueError('family/schedule stratum pairs required')
    groups=[[k for k in ids if tuple(stream_strata[k])==key] for key in keys]
    sums={k:np.zeros(len(CONTRASTS)) for k in ids};counts={k:0 for k in ids}
    for losses,owner in zip(loss_matrices,context_streams):
        sums[owner]+=contrasts(losses).mean(axis=0);counts[owner]+=1
    rng=np.random.default_rng(seed);draws=[];undefined=0
    for _ in range(samples):
        numerator=np.zeros(len(CONTRASTS));denominator=0
        for group in groups:
            for owner in rng.choice(group,size=len(group),replace=True):
                numerator+=sums[int(owner)];denominator+=counts[int(owner)]
        if denominator:draws.append(numerator/denominator)
        else:undefined+=1
    intervals=None if undefined else np.percentile(draws,[2.5,97.5],axis=0).T.tolist()
    return {'contrast_order':list(CONTRASTS),'point':(sum(sums.values())/sum(counts.values())).tolist(),
        'samples':samples,'seed':seed,'source_streams':len(ids),'strata':len(groups),
        'stratum_order':[list(k) for k in keys],'undefined_draws':undefined,
        'percentile_95':intervals,'scope':'State-weighted ratio; whole source streams resampled within strata. Secondary intervals unadjusted; no small-effect power or equivalence guarantee.'}
