# Noise Intervention Utility Coverage Protocol v1

This development extension increases stochastic-noise operational coverage
without inspecting utility labels during collection.

- Seeds begin at 430 and advance sequentially.
- Stop after 20 paired-comparable operational failures.
- Stop incomplete after at most 60 initial units.
- Successful initial rollouts do not count toward the target.
- Candidate abstention does not count as paired-comparable.
- The stopping rule may not read candidate outcome, preferred intervention,
  feature score, or evaluator label.

All policy, perturbation, probe, candidate, verification, and feature definitions
remain unchanged. Feature analysis remains threshold-free. This is development
coverage, not a held-out selector evaluation.
