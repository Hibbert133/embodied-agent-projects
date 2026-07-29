# Skill-Grounded Online Recovery Protocol

## Motivation

The completed GLM-5.1 raw-probe pilot recovered 2/5 development failures. It
selected `dominant_only` in all five cases and omitted the visible x component,
while the frozen deterministic simultaneous repair recovered 5/5. This is a
real negative result recorded in `outputs/online_planar_agent/glm51_planar_dev`.

The next experiment tests whether the failure comes from asking the model to do
continuous numerical estimation and high-level planning in the same call. It
introduces typed recovery skills while keeping task, seeds, fault, probe budget,
API-call budget, and recovery-rollout budget fixed.

## Skill contracts

The deterministic skill layer consumes only active-probe evidence and produces:

- a structured x/y action-bias estimate;
- `dominant_axis_repair`, with one nonzero correction component;
- `simultaneous_xy_repair`, with both inferred components;
- explicit preconditions, rollout cost, expected effect, verifier metrics, and
  failure modes.

The online model may select one skill, one existing correction schedule, or
stop. It cannot change correction values, output low-level actions, or access
injected fault and Oracle action fields.

## Preregistered development comparison

- task: MetaWorld `push-v3`;
- seeds: 250-254;
- injected audit condition: `(x=+0.14, y=-0.14)`;
- probes: +x/-x/+y/-y, 8 steps each;
- API calls: at most one per initial failure;
- recovery rollouts: at most one per initial failure;
- model default: GLM-5.2 through the Anthropic-compatible endpoint.

Compare:

1. GLM-5.1 raw probe interface (completed negative result);
2. GLM-5.2 skill-grounded interface;
3. frozen deterministic simultaneous recovery;
4. Oracle cancellation upper bound.

Primary outcomes are conditional recovery rate and total recovery environment
steps. Secondary outcomes are final object-goal distance, selected skill,
schedule, API latency, tokens, malformed-call rate, and verifier-compatible
predictions. A successful skill-grounding result must not be interpreted as
generalization beyond this development condition.

## Secure command

```powershell
.\scripts\run_skill_grounded_planar_agent.ps1 -Model glm-5.2 -BaseUrl https://api.modelarts-maas.com/anthropic -RunName glm52_skills_dev -ApiTimeout 300
```

The wrapper reads the key through a hidden prompt and removes it from the child
process environment in `finally`.
