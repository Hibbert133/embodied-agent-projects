# Candidate Repeatability Decision-Change Audit v1

This audit explains every case where the frozen selector changes its candidate
between one and three repeated prefixes. It does not fit a new selector.

Each changed case is classified as helpful, harmful, or neutral using the
independent full-verification outcome. The Agent-visible driver is classified
as either prefix-success priority or a robust-distance rank flip. Agent evidence
and evaluator outcome fields remain separate until audit scoring.

All changed cases are reported. Representative cases are selected mechanically
within each outcome class by the largest absolute k=3 robust-score margin, with
seed as the tie-break. This rule is fixed before case-level inspection and may
later be used for video rendering.
