# ProbeMem-SciAgent API Reliability v1.1

Status: `IMPLEMENTED_NOT_EXECUTED`

This shadow-only successor adds evidence-grounding certificates, a no-environment
API health-check, canonical request fingerprints, validated-response caching, a
two-failure circuit breaker, and separate transport/schema/semantic audit.

No model action may execute, no memory or principle may be written, and no
recovery claim is permitted. Live execution requires configured GLM credentials,
a completely clean worktree, a committed immutable manifest, and fresh seeds
5850--5899. No seed in that range has been executed.

Current preflight on 2026-08-06 stopped before manifest generation because the
worktree contains an unrelated untracked `.vscode/` directory. Both
`ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` were also unset. This is an
infrastructure blocker, not an API-validity or recovery result; API calls,
initial units, and consumed fresh seeds remain zero.
