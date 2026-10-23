# ProbeMem Phase C Intervention-Utility Audit

Source run: `probemem_phase_c_20260731T155344Z_f7176579eb82`
Source manifest: `97fffbc4fe1c44b8b920b791d621bd574678c56593edd8312e91ec142e3582e0`
Source method: `verified_episodic_retrieval`

## Result

The audit created 10 falsifiable action-conditional records without new API calls or environment rollouts. Fresh verification supported the executed skill in 5 cases, contradicted it in 2, and remained unresolved in 3.

The predicted verification status matched in 5 cases and produced 5 negative surprises. There were no positive surprises.

## Scientific boundary

Every record concerns `BOUNDED_PLANAR_COMPENSATION`; there are no matched counterfactual skill pairs. These records can identify failed predictions and contradictions for the executed skill, but cannot establish that another registered skill would have been better. They are development audit records, not actionable episodic memory, and all principle-promotion flags are false.

## Next registered question

On new development seeds, execute matched fresh verification for the two existing intervention families from the same initial failure. Test whether Agent-visible applicability signatures separate which skill wins. Do not use the current held-out seeds or promote an LLM-generated principle first.

## Reproduction

```bash
python scripts/build_probemem_intervention_utility_audit.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T155344Z_f7176579eb82"
```
