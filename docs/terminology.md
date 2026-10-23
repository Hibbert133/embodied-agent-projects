# Canonical Terminology

| Canonical term | Meaning | Legacy wording |
|---|---|---|
| Embodied Research Agent | High-level system that acquires evidence and tests hypotheses | recovery agent |
| diagnostic agent | Maintains and revises mechanism hypotheses | failure classifier |
| evidence acquisition decision | Explicit choice to probe, update, or abstain | automatic probing |
| diagnostic probe | Bounded interaction designed to reduce uncertainty | probe rollout |
| hypothesis | Falsifiable mechanism explanation with confidence and evidence | failure label |
| corrective intervention | Bounded change proposed from a hypothesis | repair / correction |
| verification rollout | Fresh rollout testing declared intervention criteria | retry |
| verified experience | Accepted hypothesis-intervention-outcome record | memory item |

Historical reports and CSV schemas retain their original wording. This preserves
the reproducibility and meaning of completed experiments. New public interfaces,
README sections, and future reports use the canonical vocabulary.
