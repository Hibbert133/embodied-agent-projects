"""Bounded Anthropic-compatible Research Agent for recovery-system search."""
from __future__ import annotations
import hashlib, json, os
from time import perf_counter
from typing import Any, Mapping, Sequence
from src.autoresearch import ResearchProposal, RecoveryPolicyConfig
from src.online_planar_agent import validate_agent_payload

PROMPT_VERSION = "budgeted-recovery-autoresearch-v1"
SYSTEM_PROMPT = """You are a robotic-agent research scientist conducting bounded
system-level experimentation, not controlling the robot. Propose exactly two
configs from the supplied discrete search space. Ground each change in observed
agent-visible counterexamples and state one falsifiable hypothesis. Never infer
or request injected fault labels. Do not generate code, actions, or parameters
outside the schema. Return exactly one JSON object."""

def extract_object(text: str) -> Mapping[str, Any]:
    decoder=json.JSONDecoder(); found=[]
    for i,c in enumerate(text):
        if c!="{": continue
        try: value,_=decoder.raw_decode(text[i:])
        except json.JSONDecodeError: continue
        if isinstance(value,dict) and "candidates" in value and value not in found: found.append(value)
    if len(found)!=1: raise ValueError(f"expected one research proposal, found {len(found)}")
    return found[0]

def parse_proposal(value: Mapping[str, Any]) -> ResearchProposal:
    try:
        raw=value["candidates"]
        if not isinstance(raw,list) or len(raw)!=2: raise ValueError("exactly two candidates required")
        candidates=tuple(RecoveryPolicyConfig.from_mapping(x) for x in raw)
        return ResearchProposal(
            candidates=(candidates[0],candidates[1]), hypothesis=str(value["hypothesis"]),
            targeted_counterexample_ids=tuple(str(x) for x in value["targeted_counterexample_ids"]),
            expected_metric_change=str(value["expected_metric_change"]),
        )
    except (KeyError,TypeError,ValueError) as exc: raise ValueError(f"invalid research proposal: {exc}") from exc

class AnthropicResearchAgent:
    def __init__(self, *, model:str="glm-5.2", base_url:str|None=None, timeout_seconds:float=300,
                 max_retries:int=2, max_tokens:int=1400, client:Any|None=None) -> None:
        if not model.strip() or timeout_seconds<=0 or max_retries<0 or max_tokens<=0: raise ValueError("valid request limits required")
        self.model=model; self.base_url=base_url or os.environ.get("ANTHROPIC_BASE_URL"); self.timeout_seconds=float(timeout_seconds)
        self.max_retries=int(max_retries); self.max_tokens=int(max_tokens); self._client=client
        self.prompt_hash=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
    def _get_client(self) -> Any:
        if self._client is not None: return self._client
        key=os.environ.get("ANTHROPIC_API_KEY")
        if not key or not self.base_url: raise RuntimeError("ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required")
        try: from anthropic import Anthropic
        except ImportError as exc: raise RuntimeError("install dependencies from requirements.txt") from exc
        self._client=Anthropic(api_key=key,base_url=self.base_url,timeout=self.timeout_seconds,max_retries=self.max_retries); return self._client
    def propose(self, *, agent_cases:Sequence[Mapping[str,Any]], prior_results:Sequence[Mapping[str,Any]],
                search_space:Mapping[str,Any], round_id:int) -> tuple[ResearchProposal,dict[str,Any]]:
        if round_id<=0 or not agent_cases: raise ValueError("positive round and agent cases required")
        validate_agent_payload(*agent_cases)
        payload={"task":"improve leakage-safe push-v3 recovery interaction efficiency","prompt_version":PROMPT_VERSION,
                 "round":round_id,"agent_visible_cases":list(agent_cases),"prior_candidate_results":list(prior_results),
                 "bounded_search_space":dict(search_space),"objective_order":["recovery_success","environment_steps","abstention_quality"],
                 "response_schema":{"candidates":"exactly two complete config objects","hypothesis":"falsifiable string",
                 "targeted_counterexample_ids":"non-empty list of supplied case IDs","expected_metric_change":"measurable prediction"}}
        start=perf_counter()
        try:
            response=self._get_client().messages.create(model=self.model,max_tokens=self.max_tokens,system=SYSTEM_PROMPT,
                messages=[{"role":"user","content":json.dumps(payload,ensure_ascii=False)}])
        except Exception as exc: raise RuntimeError(f"Anthropic-compatible research request failed: {exc}") from exc
        latency=(perf_counter()-start)*1000
        text="".join(str(getattr(b,"text","")) for b in getattr(response,"content",()) if getattr(b,"type",None)=="text").strip()
        try: proposal=parse_proposal(extract_object(text))
        except ValueError as exc: raise RuntimeError(f"invalid research-agent response: {exc}") from exc
        valid_ids={str(c["case_id"]) for c in agent_cases}
        if not set(proposal.targeted_counterexample_ids)<=valid_ids: raise RuntimeError("proposal targets unknown counterexample IDs")
        usage=getattr(response,"usage",None)
        audit={"provider":"anthropic-compatible","response_id":getattr(response,"id",""),"model":getattr(response,"model",self.model),
               "base_url":self.base_url or "","prompt_version":PROMPT_VERSION,"prompt_hash":self.prompt_hash,"latency_ms":latency,
               "usage":{k:getattr(usage,k) for k in ("input_tokens","output_tokens") if usage is not None and hasattr(usage,k)}}
        return proposal,audit
