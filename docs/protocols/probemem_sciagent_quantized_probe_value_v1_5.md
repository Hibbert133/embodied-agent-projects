# ProbeMem-SciAgent Quantized Probe Value v1.5

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Question and prior result

Probe Value v1.4 retained transport and categorical capability validity but
failed its numerical EVSI certificate. This successor asks whether a smaller,
complete 5%-probability token language permits coherent, budget-sensitive
probe-value statements without weakening Host validation.

Seeds 6300--6349 and all earlier results are immutable. Seeds 6200--6299 and
6350--6449 remain reserved. This protocol may scan fresh development seeds
6450--6499 once; 6500--6599 are reserved.

## Single method change

Every probability is selected from the 21-token lattice `P_00` through `P_20`,
representing 0.00 through 1.00 in increments of 0.05. A probe request supplies:

- the selected registered probe token;
- current probabilities for the provisional decision skill and its alternative;
- exactly two registered outcome branches;
- one branch-probability token and two candidate-probability tokens per branch.

The model no longer outputs claimed gain, branch final skills, normalization,
argmax, cost, or admission. The Host derives all of them. The provisional skill
probability must be at least the alternative probability. Branch probabilities
must each be at least 0.05 and sum exactly to 1.00. A non-probe decision must
return a null probe-value certificate.

The Host retains the v1.4 calculation and fixed costs. Admission requires a
positive probability of a branch changing the skill and expected value gain
strictly greater than 64/1256 for compensation probe or 192/1256 for retry
probe. Invalid tokens or inconsistent structures fail closed.

## Boundary and gate

After one health check, scan at most 50 units until eight operational failures
are collected. The maximum is nine primary calls, one repair, ten total calls,
and zero transport retries. No micro-probe or recovery action executes; no
paired outcome, memory, or principle is collected.

Passing requires the v1.3 interface gate, at least seven valid quantized-value
certificates, at least four rejected probe requests, probe admission rate no
greater than 50%, and zero integrity violations. This is an interface and
budget-expression gate only. Passing cannot authorize robot actions, recovery
claims, memory, principles, validation, or held-out execution. Failure is
preserved without changing the probability lattice, prompt, costs, gate, or
seeds.
