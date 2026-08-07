"""Subprocess-isolated API transport with a host-enforced wall-clock deadline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Sequence

from src.probemem_sciagent.api_envelope import EnvelopeTolerantApiReliabilityClient


def execute_subprocess_with_hard_deadline(
    command: Sequence[str], *, input_text: str, deadline_seconds: float,
) -> str:
    if deadline_seconds <= 0:
        raise ValueError("hard deadline must be positive")
    try:
        completed = subprocess.run(
            list(command), input=input_text, capture_output=True, text=True,
            timeout=deadline_seconds, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"API hard deadline exceeded: {deadline_seconds:.3f}s") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"worker exit {completed.returncode}"
        raise RuntimeError(f"hard-deadline worker failed: {detail}")
    return completed.stdout


class HardDeadlineEnvelopeClient(EnvelopeTolerantApiReliabilityClient):
    """Envelope client whose every API call runs in a killable child process."""

    def __init__(self, *, hard_deadline_seconds: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if hard_deadline_seconds <= 0:
            raise ValueError("hard deadline must be positive")
        self.hard_deadline_seconds = hard_deadline_seconds

    def _create_message_response(self, **kwargs: Any) -> Any:
        if not self.base_url:
            raise RuntimeError("ANTHROPIC_BASE_URL is required")
        request = json.dumps({
            "model": self.model, "base_url": self.base_url,
            "timeout_seconds": min(self.timeout_seconds, self.hard_deadline_seconds),
            "message_kwargs": kwargs,
        })
        raw_result = execute_subprocess_with_hard_deadline(
            [sys.executable, "-m", "src.probemem_sciagent.hard_deadline_transport", "--worker"],
            input_text=request, deadline_seconds=self.hard_deadline_seconds,
        )
        payload = json.loads(raw_result)
        if not isinstance(payload, dict) or set(payload) != {"raw", "usage"}:
            raise RuntimeError("hard-deadline worker returned invalid schema")
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=payload["raw"])],
            usage=SimpleNamespace(**payload["usage"]),
        )


def _worker_main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is unavailable in API worker")
        from anthropic import Anthropic
        client = Anthropic(
            api_key=key, base_url=request["base_url"],
            timeout=float(request["timeout_seconds"]), max_retries=0,
        )
        response = client.messages.create(**request["message_kwargs"])
        raw = "".join(
            str(getattr(block, "text", "")) for block in getattr(response, "content", ())
            if getattr(block, "type", None) == "text"
        ).strip()
        usage = getattr(response, "usage", None)
        result = {
            "raw": raw,
            "usage": {
                name: int(getattr(usage, name)) for name in ("input_tokens", "output_tokens")
                if usage is not None and hasattr(usage, name)
            },
        }
        sys.stdout.write(json.dumps(result))
        return 0
    except BaseException as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not args.worker:
        parser.error("--worker is required")
    return _worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
