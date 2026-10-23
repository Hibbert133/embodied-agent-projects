# ProbeMem-SciAgent Robust Probe Value v1.6

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Question

Quantized Probe Value v1.5 improved numerical certificate validity but remained
incomplete because the compatibility SDK did not enforce its configured timeout.
All three valid partial assessments also admitted a probe. This successor asks
whether ambiguity-aware robust value, rather than nominal self-reported EVSI,
can reject nonessential probes while retaining the complete token contract.

The incomplete v1.5 stream is immutable. Seeds 6450--6499 cannot be completed.
All earlier reserves, including 6500--6599, remain blocked. This protocol may
scan fresh seeds 6600--6649 once; 6650--6749 are reserved.

## Transport integrity correction

Every API call runs in a dedicated child process. The Host invokes that process
with a 210-second `subprocess.run` deadline, zero transport retries, and no API
key in command arguments or files. Timeout kills the child and becomes an
audited fail-closed call. This external deadline is required to execute the
bounded protocol; it is not a model-performance variable.

## Robust value rule

The v1.5 5%-probability token language remains. The Host admits a requested
probe only when all conditions hold:

1. current selected-minus-alternative probability is no greater than 0.10;
2. the two registered probe outcomes derive different final skills;
3. candidate probabilities are reduced by the frozen 0.025 quantization half-
   width while current selected probability is increased by 0.025;
4. this lower-bound expected utility gain is strictly greater than the fixed
   normalized probe cost.

The model does not output robust gain, final skills, cost, or admission. The
Host derives them. Non-probe decisions require a null value certificate.

## Population, gate, and boundary

After one health check, scan at most 50 units until eight operational failures.
The maximum is nine primary calls, one repair, ten calls, and zero retries.
Passing requires at least seven fully certified decisions and value assessments,
at least four rejected probe requests, admission rate at most 50%, at most one
fail-closed output, at most one repair, and zero integrity violations.

No proposed probe or recovery skill executes. No paired outcome, memory,
hypothesis, or principle is collected. Passing supports only bounded robust-
value interface feasibility; it cannot authorize recovery, online learning,
validation, held-out execution, or principle promotion. Failure or incomplete
status is preserved without changing the deadline, robust bounds, gate, or
seeds.
