"""Fail-closed extraction of one certified JSON object from API prose."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any, Mapping

from src.probemem_sciagent.api_reliability import ApiReliabilityClient
from src.probemem_sciagent.capability_contract import expand_capability_response
from src.probemem_sciagent.probe_value import validate_probe_value_certificate
from src.probemem_sciagent.quantized_probe_value import (
    QUANTIZED_CONTRACT_VERSION,
    validate_quantized_probe_value_certificate,
)
from src.probemem_sciagent.robust_probe_value import (
    ROBUST_CONTRACT_VERSION,
    validate_robust_probe_value_certificate,
)


CERTIFIED_TOP_LEVEL_KEYS = {"decision", "certificate"}


def extract_unique_certified_object(
    text: str, *, expected_keys: set[str] | frozenset[str] = CERTIFIED_TOP_LEVEL_KEYS,
) -> tuple[Mapping[str, Any], str]:
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
    if isinstance(bare, Mapping) and set(bare) == set(expected_keys):
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
        if not isinstance(value, Mapping) or set(value) != set(expected_keys):
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
            response = self._create_message_response(
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
            probe_contract = request_payload.get("probe_value_contract")
            expected_keys = (
                CERTIFIED_TOP_LEVEL_KEYS | {"probe_value_certificate"}
                if probe_contract is not None else CERTIFIED_TOP_LEVEL_KEYS
            )
            mapping, extraction_mode = extract_unique_certified_object(
                raw, expected_keys=expected_keys,
            )
            mapping = dict(mapping)
            raw_probe_value = mapping.pop("probe_value_certificate", None)
            contract = request_payload.get("capability_contract")
            capability_applied = contract is not None
            if capability_applied:
                try:
                    mapping = expand_capability_response(mapping, contract)
                except Exception as exc:
                    self.audit.append({
                        "phase": phase, "repair": repair, "valid_transport": True,
                        "extraction_mode": extraction_mode,
                        "capability_contract_applied": True,
                        "valid_capability_contract": False,
                        "latency_ms": (perf_counter() - started) * 1000.0,
                        "usage": usage_payload, "error": f"{type(exc).__name__}: {exc}",
                        "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    })
                    raise _RecordedCapabilityError(str(exc)) from exc
            probe_assessment = None
            if probe_contract is not None:
                try:
                    if not isinstance(contract, Mapping):
                        raise ValueError("probe value certificate requires capability contract")
                    if probe_contract.get("contract_version") == ROBUST_CONTRACT_VERSION:
                        probe_assessment = validate_robust_probe_value_certificate(
                            raw_probe_value, decision=mapping["decision"],
                            capability_contract=contract, probe_value_contract=probe_contract,
                        )
                    elif probe_contract.get("contract_version") == QUANTIZED_CONTRACT_VERSION:
                        probe_assessment = validate_quantized_probe_value_certificate(
                            raw_probe_value, decision=mapping["decision"],
                            capability_contract=contract, probe_value_contract=probe_contract,
                        )
                    else:
                        if not isinstance(raw_probe_value, Mapping):
                            raise ValueError("probe value certificate must be an object")
                        probe_assessment = validate_probe_value_certificate(
                            raw_probe_value, decision=mapping["decision"],
                            capability_contract=contract, probe_value_contract=probe_contract,
                        )
                except Exception as exc:
                    self.audit.append({
                        "phase": phase, "repair": repair, "valid_transport": True,
                        "extraction_mode": extraction_mode,
                        "capability_contract_applied": capability_applied,
                        "valid_capability_contract": True,
                        "probe_value_contract_applied": True,
                        "valid_probe_value_certificate": False,
                        "latency_ms": (perf_counter() - started) * 1000.0,
                        "usage": usage_payload, "error": f"{type(exc).__name__}: {exc}",
                        "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    })
                    raise _RecordedProbeValueError(str(exc)) from exc
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": True,
                "extraction_mode": extraction_mode,
                "capability_contract_applied": capability_applied,
                "valid_capability_contract": True,
                "probe_value_contract_applied": probe_contract is not None,
                "valid_probe_value_certificate": None if probe_contract is None else True,
                "probe_value_assessment": None if probe_assessment is None else probe_assessment.to_dict(),
                "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload,
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            return mapping
        except (_RecordedCapabilityError, _RecordedProbeValueError):
            raise

        except Exception as exc:
            self.audit.append({
                "phase": phase, "repair": repair, "valid_transport": False,
                "extraction_mode": "REJECTED",
                "capability_contract_applied": "capability_contract" in request_payload,
                "valid_capability_contract": False,
                "probe_value_contract_applied": "probe_value_contract" in request_payload,
                "valid_probe_value_certificate": (
                    False if "probe_value_contract" in request_payload else None
                ),
                "latency_ms": (perf_counter() - started) * 1000.0,
                "usage": usage_payload, "error": f"{type(exc).__name__}: {exc}",
                "response_hash": hashlib.sha256(raw.encode()).hexdigest(),
            })
            raise

    def _create_message_response(self, **kwargs: Any) -> Any:
        return self._get_client().messages.create(**kwargs)


class _RecordedCapabilityError(ValueError):
    """Internal marker preventing duplicate audit rows after token rejection."""


class _RecordedProbeValueError(ValueError):
    """Internal marker preventing duplicate audit rows after EVSI rejection."""
