"""Research-oriented evaluation schemas and protocol metrics."""

from src.evaluation.campaign import (
    CampaignBudget,
    CampaignJob,
    CampaignLedger,
    CampaignOutcome,
    CampaignRunSummary,
    run_campaign,
)
from src.evaluation.intervention_utility import (
    CandidateUtilityOutcome,
    UtilityComparison,
    best_candidate_ids,
    compare_candidate_utility,
)
from src.evaluation.metrics import ResearchMetrics

from src.evaluation.allocation_metrics import (
    accuracy,
    average_precision,
    balanced_accuracy,
    paired_win_tie_loss,
    roc_auc,
    stratified_paired_bootstrap_difference,
    wilson_interval,
)

__all__ = [
    "CampaignBudget",
    "CampaignJob",
    "CampaignLedger",
    "CampaignOutcome",
    "CampaignRunSummary",
    "ResearchMetrics",
    "CandidateUtilityOutcome",
    "UtilityComparison",
    "accuracy",
    "average_precision",
    "balanced_accuracy",
    "best_candidate_ids",
    "compare_candidate_utility",
    "paired_win_tie_loss",
    "roc_auc",
    "stratified_paired_bootstrap_difference",
    "wilson_interval",
    "run_campaign",
]
