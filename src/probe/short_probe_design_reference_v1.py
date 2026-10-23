"""Standard local D-optimal four-step software reference, not task evidence.

The only input is a task-specific nominal response model. Scores use the
observed-four-response marginal covariance at identity, not a fitted actuator
or a future task outcome. No simulator, optimizer or random source is called.
"""
from itertools import combinations, permutations
import math

import numpy as np

from src.probe.cold_start_response import clipped_normal_mean, validate_model


def candidate_programs():
    """144 ordered programs: two distinct antipodal pairs from eight directions.

    Diagonal float32 components round toward zero if needed so every actual
    vector norm is bounded by float32(.4). Return actual values and energies;
    diagonal and axial norms differ by at most float32 rounding.
    """
    amplitude = np.float32(.4)
    diagonal = np.float32(float(amplitude)/math.sqrt(2))
    while math.hypot(float(diagonal), float(diagonal)) > float(amplitude):
        diagonal = np.nextafter(diagonal, np.float32(0))
    axes = ((amplitude, 0), (0, amplitude), (diagonal, diagonal), (diagonal, -diagonal))
    directions = np.asarray([(sign*x, sign*y, 0, 0) for x, y in axes for sign in (1, -1)], dtype=np.float32)
    programs = []
    for first, second in combinations(range(4), 2):
        for order in permutations((2*first, 2*first+1, 2*second, 2*second+1)):
            commands = directions[list(order)].astype(float)
            programs.append({'candidate_id': f'FOUR_{len(programs):03d}', 'direction_ids': list(order),
                'commands': commands.tolist(), 'command_norms': np.linalg.norm(commands[:, :2], axis=1).tolist(),
                'total_squared_xy_norm': float(np.sum(commands[:, :2]**2))})
    return programs


def design_four(saved):
    """Enumerate all local information scores; use first exact-score maximizer.

    This is a classical design baseline. Its local information criterion is
    neither physical probability qualification nor predicted task utility.
    The future task executor must consume the saved selected program unchanged.
    """
    _, impulse, covariance = validate_model(saved)
    impulse = impulse[:8, :8]
    chol = np.linalg.cholesky(covariance[:8, :8])
    identity = np.array([[1., 0, 0], [0, 1., 0]])
    basis = np.eye(6)
    candidates = candidate_programs()
    selected = None
    for candidate in candidates:
        x = np.c_[np.asarray(candidate['commands'])[:, :2], np.ones(4)]
        _, slope = clipped_normal_mean(x@identity.T)
        try:
            with np.errstate(over='raise', invalid='raise', divide='raise'):
                jacobian = np.column_stack([impulse@((x@row.reshape(2, 3).T)*slope).ravel() for row in basis])
                whitened = np.linalg.solve(chol, jacobian)
                if not np.isfinite(whitened).all():
                    raise ValueError('nonfinite nominal design information')
                singular = np.linalg.svd(whitened, compute_uv=False)
                tolerance = max(whitened.shape)*np.finfo(float).eps*singular[0]
                rank = int(np.sum(singular > tolerance))
                score = float(2*np.log(singular).sum()) if rank == 6 else None
        except (FloatingPointError, np.linalg.LinAlgError) as error:
            raise ValueError('nominal design information could not be evaluated') from error
        candidate.update(whitened_design_rank=rank, logdet_information=score,
            information_condition_number=float((singular[0]/singular[-1])**2) if rank == 6 else None)
        if score is not None and (selected is None or score > selected['logdet_information']):
            selected = candidate
    return {'schema': 'local_d_optimal_four_v1', 'task': saved['task'],
        'scope': 'NOMINAL_IDENTITY_FOUR_RESPONSE_MARGINAL_SOFTWARE_REFERENCE',
        'physical_response_qualified': False, 'probability_guarantee': False,
        'task_utility_qualified': False, 'operating_parameters': identity.ravel().tolist(),
        'tie_rule': 'FIRST_ENUMERATED_EXACT_SCORE_MAXIMIZER',
        'command_norm_bound': float(np.float32(.4)), 'candidate_count': len(candidates),
        'selected_candidate_id': None if selected is None else selected['candidate_id'],
        'reason': 'NO_IDENTIFIABLE_NOMINAL_DESIGN' if selected is None else 'LOCAL_D_OPTIMAL_REFERENCE',
        'candidates': candidates}
