# Online Planar Agent Protocol

## Question

Can an online high-level Agent use leakage-safe episode and active-probe evidence
to choose a planar repair mode, correction vector, and task-phase schedule under
a one-rollout budget? The intended comparison is against the frozen deterministic
simultaneous repair, not against an unconstrained language-model controller.

## Agent action space

The online model does not output robot actions. One API call selects:

- `repair_mode`: dominant-only, simultaneous, or stop;
- bounded x/y correction components from the existing quantized grid;
- `whole`, `push_only`, or `phase_aware` correction schedule;
- a hypothesis, expected measurable effect, and confidence.

The adapter rejects Oracle action fields, injected-bias labels, fault labels,
out-of-grid corrections, malformed mode/vector combinations, and ambiguous JSON.
It records model, prompt version/hash, response ID, latency, and token usage,
without recording credentials.

## First pilot

The development pilot is frozen to seeds 250-254 and bias `(x=+0.14,y=-0.14)`.
Each initial failure receives four 8-step symmetric probes, at most one API call,
and at most one recovery rollout. Compare its conditional recovery rate, final
distance, and total recovery environment steps with the deterministic values in
`outputs/planar_bias_pilot/xpos014_yneg014_dev/summary.csv`.

No online result is reported yet because the current process did not contain an
API credential. This protocol and its mock integration tests are engineering
readiness evidence only.

## Secure reproduction

Run the wrapper and enter a newly issued key at the hidden prompt:

```powershell
.\scripts\run_online_planar_agent.ps1 -Model glm-5.1 -BaseUrl https://api.modelarts-maas.com/anthropic -RunName glm51_planar_dev
```

The key exists only in the child process environment and is removed in `finally`.
Do not paste it into chat, commands, configuration files, reports, or Git.
