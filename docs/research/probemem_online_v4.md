# ProbeMem-Online v4

ProbeMem-Online studies whether a rollout-level GLM agent can map repeated-probe
evidence and chronological action-outcome memory to bounded recovery skills in
persistent execution regimes. It does not update policy weights or produce
continuous actions.

The execution order is Gate A interface grounding, Gate B memory integrity,
Gate C chronological online adaptation, and only then a separately frozen
principle experiment. A failed gate is preserved and blocks dependent claims.

ProbeMem-ACR v3 remains immutable: the deterministic repeated-probe rule reached
33/40 accepted with zero harmful selections, while the ten-call GLM pilot
recognized stable bias but abstained on four recoverable stochastic cases.
Earlier state-only, accepted-only, and coverage-aware memory failures remain the
motivation for action-conditioned outcome memory.

Gate A subsequently passed on 30 fresh shadow cases. Compact evidence plus
explicit skill semantics selected the registered target skill in 27/30 cases,
including retry in 12/15 stochastic cases with zero stochastic abstentions,
versus 22/30 correct and five stochastic abstentions for the historical full
payload. This authorizes only Gate B infrastructure. It is not an online
execution or memory-benefit result.

## Gate C development result

The immutable chronological Gate C run
`probemem_online_gate_c_20260803T095434Z_f346d23912a9` completed all 60
operational cases. The full resonance-aware Agent changed 12 of 60 stateless
GLM decisions, but only four changes were helpful and three were harmful. It
recovered 41/60 cases, compared with 40/60 for stateless GLM and 43/60 for the
frozen variance rule. Its paired accepted-recovery difference from stateless
GLM was +1/60, with a deterministic paired-bootstrap 95% interval spanning
-4/60 to +6/60. Post-shift recovery was lower than stateless GLM (24/39 versus
27/39).

The preregistered Gate C promotion criteria therefore failed: net helpful
memory changes were +1 rather than at least +3, harmful transfer decreased by
10% rather than at least 30%, and recovery was two cases below the strongest
non-Oracle deterministic baseline. This is evidence that action-conditioned
memory crossed the reasoning-to-action boundary, but not that it reliably
improved online recovery. Principle generation, validation, and held-out
execution remain blocked. The complete claim-bounded analysis is recorded in
`reports/probemem_online_gate_c_development.md`.

The subsequent offline audit reconstructed the prior-only memory snapshots for
all 12 action changes without new rollout or API calls. Three of four helpful
changes merely restored the action already selected by the frozen variance
rule. All three harmful changes overrode high-confidence retry decisions after
both global and recent Memory summaries favored compensation. Thus Memory
agreement alone is not a sufficient applicability test. The only helpful
override beyond the deterministic rule occurred close to its frozen boundary.

The separately registered successor is therefore selective rather than
all-case GLM use. Protocol
`docs/protocols/probemem_online_selective_override_development_v1.md` protects
decisions stable under leave-one-probe-repeat-out analysis and invokes GLM plus
Memory only for measurement-ambiguous cases. It uses fresh development seeds
4500--4599 and must not derive a numeric ambiguity band from the 12 audited
outcomes.

The selective-override run later reached 40 operational cases but found only
three leave-one-repeat-out ambiguous cases, below the frozen minimum of ten. It
is immutably `INCOMPLETE_POPULATION`. The primary Memory-fallback method tied
the frozen rule at 34/40 accepted while using nine API calls instead of the
120-call all-case reference. Its two action changes were outcome ties. This is
descriptive evidence for API-cost reduction, not Memory or GLM recovery
benefit. Do not widen the ambiguity definition, extend seeds 4500--4599, or
advance to validation, held-out execution, or principles.
