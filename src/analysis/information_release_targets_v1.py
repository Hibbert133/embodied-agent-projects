"""Standard randomized-release AIPW targets, not a new statistical estimator.

Truthful post-return randomization, fixed receiver versions and honest nuisance
fits are external design conditions; passing this numerical interface cannot
establish them or a robot safety/task-benefit guarantee.
"""
from src.probe.information_release_v1 import numeric,validate_receipt,ended
from src.probe.task_passive_pi_v1 import require


def targets(*,saved_return,release_receipt,cutoff_loss,mu_masked,mu_full,expected_receiver_version,
            independent_group,nuisance_training_groups,expected_probability):
    _,after=validate_receipt(saved_return,release_receipt)
    binding=release_receipt['binding'];release=binding['assigned_exposure'];p=binding['assignment_probability']
    require(p==numeric(expected_probability) and 0<p<1,'propensity equals the independently frozen assignment protocol')
    y=numeric(cutoff_loss,0,500);m0=numeric(mu_masked,0,500);m1=numeric(mu_full,0,500)
    receiver_version=binding['receiver_version']
    require(type(receiver_version) is str and len(receiver_version)==64 and all(c in '0123456789abcdef' for c in receiver_version)
            and receiver_version==expected_receiver_version,'outcome labels bound to the actually executed frozen receiver')
    require(type(independent_group) is str and independent_group and type(nuisance_training_groups) in (tuple,list)
            and all(type(g) is str and g for g in nuisance_training_groups) and len(set(nuisance_training_groups))==len(nuisance_training_groups)
            and independent_group not in nuisance_training_groups,'nuisance fitting must exclude this entire independent group')
    terminal=ended(after) or after.completed_steps==500
    if terminal:require(y==(after.completed_steps if after.current.success else 500),'known pre-release terminal loss must match real state')
    identical=terminal or release_receipt['model_view']['common']['paid_acquisition_steps']==0
    if identical:
        masked=full=y;increment=0.
    else:
        masked=m0+(0. if release else (y-m0)/(1-p))
        full=m1+((y-m1)/p if release else 0.)
        increment=full-masked
    return dict(schema='RANDOMIZED_SIGNAL_EFFECT_TARGETS_V1',masked_full_program_risk=masked,
        supplemental_information_effect=increment,released_full_program_risk=full,
        pseudo_targets_clipped=False,receiver_version=receiver_version,
        known_before_release_terminal=terminal,identical_views_or_pre_release_terminal=identical,
        statistical_unbiasedness_not_verified_by_schema=True)


def complete_program_score(masked_risk,information_effect,expose):
    """Acquisition, validation, movement and failure are already in both targets."""
    require(type(expose) is bool,'registered exposure choice')
    base=numeric(masked_risk);effect=numeric(information_effect)
    return base+(effect if expose else 0.)
