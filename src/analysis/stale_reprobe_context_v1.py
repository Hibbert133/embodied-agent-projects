"""Evaluator-only actuator switch before relocation; never an actor input."""
from copy import deepcopy
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.probe.cache_acquisition_evidence_v1 import digest


def install_context(session, source, target, *, planned_boundary):
    if type(session) is not ProbeSession or not session.alive() or session.ctx["calls"] != planned_boundary or planned_boundary not in (16,32,64):
        raise ValueError("live registered pre-reprobe boundary required")
    if session._pending is not None or getattr(session,"_stale_context_installed",False) or getattr(session,"_physical_reprobe_consumed",False):
        raise ValueError("context switch must occur once, before physical reacquisition")
    if session.captures or session.restores or session._snapshots or digest(session.fault) != digest(source):
        raise ValueError("unmodified continuous source and original actuator required")
    before = session.witness();ledger = session.ledger.snapshot();noise = session.ctx["noise_rows"]
    calls = session.ctx["calls"];queries = session.policy_queries
    payload = {**session.branch,"at_calls":calls,"source_fault_oracle":deepcopy(source),
        "target_fault_oracle":deepcopy(target),"ledger":ledger,**before}
    intent = session.emit("EVALUATOR_FAULT_SET_INTENT",payload)
    if any(digest(intent.get(k)) != digest(v) for k,v in payload.items()): raise ValueError("saved evaluator context changed")
    session._stale_context_installed = True
    session.fault = deepcopy(intent["target_fault_oracle"])
    if (session.witness() != before or session.ledger.snapshot() != ledger or session.ctx["noise_rows"] is not noise
            or session.ctx["calls"] != calls or session.policy_queries != queries):
        raise ValueError("context update changed world, noise, query count or physical cost")
    complete = session.emit("EVALUATOR_FAULT_SET_COMPLETE",{**session.branch,"intent_sequence":intent["sequence"],
        "at_calls":calls,"active_fault_oracle":deepcopy(session.fault),"ledger":ledger,**before})
    return {"intent_sequence":intent["sequence"],"complete_sequence":complete["sequence"],"at_calls":calls,
        "source_fault_oracle":deepcopy(source),"active_fault_oracle":deepcopy(session.fault)}
