"""Fail-closed extraction of one certified JSON object from API prose."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any, Mapping

from src.probemem_sciagent.api_reliability import ApiReliabilityClient


CERTIFIED_TOP_LEVEL_KEYS = {"decision", "certificate"}


def extract_unique_certified_object(text: str) -> tuple[Mapping[str, Any], str]:
    """Return one unambiguous certified object and its envelope class.

    Bare JSON remains preferred. Compatibility-model prose or Markdown is
    accepted only when scanning the complete response finds exactly one unique
    object with the certified top-level keys. Nested decision/certificate
    objects therefore cannot become independent candidates.
    """

    stripped = text.strip()
    try:
        bare = json.loads(stripped)
    except json.JSONDecodeError:
        bare = None
    if isinstance(bare, Mapping) and set(bare) == CERTIFIED_TOP_LEVEL_KEYS:
        return bare, "BARE_JSON"

    decoder = json.JSONDecoder()
    candidates: dict[str, Mapping[str, Any]] = {}
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, Mapping) or set(value) != CERTIFIED_TOP_LEVEL_KEYS:
            continue
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
        candidates[canonical] = value
    if not candidates:
        raise ValueError("response contains no certified JSON object")
    if len(candidates) != 1:
        raise ValueError(f"response contains {len(candidates)} ambiguous certified JSON objects")
    return next(iter(candidates.values())), "WRAPPED_UNIQUE_JSON"


class EnvelopeTolerantApiReliabilityClient(ApiReliabilityClient):
    """v1.2 transport adapter; certificate and semantic guards are unchanged."""

    def _request(
        self, payload: Mapping[str, Any], *, phase: str, system: str,
        repair: bool, previous_error: str | None,
    ) -> Mapping[str, Any]:
        self.call_budget.consume(repair=repair)
        request_payload = dict(payload)
        if repair:
            request_payload["schema_repair"] = {
                "previous_error": previous_error,
                "instruction": "Return corrected JSON only.",
            }
        started = perf_counter()
        raw = ""
        usage_payload: dict[str, int] = {}
        try:
            response = self._get_client().messages.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.0,
                system=system,
                messages=[{"role": "user", "content": json.dumps(request_payload)}],
            )
            raw = "".join(
                str(getattr(block, "text", "")) for block in getattr(response, "content", ())
                if getattr(block, "type", None) == "text"
            ).strip()
            usage = getattr(response, "usage", None)
            usage_payload = {
                name: int(getattr(usage, name)) for name in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, name)
            }
            mapping, extraction_mode = extract_unique_certified_object(raw)
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": True,
                "extraction_mode": extraction_mode,
                "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload,
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            return mapping
        except Exception as exc:
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": False,
                "extraction_mode": "REJECTED",
                "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload, "error": f"{type(exc).__name__}: {exc}",
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            raise
