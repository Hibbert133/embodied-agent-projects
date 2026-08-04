# ProbeMem-Online Superseded Interruption Note

Run ID: `probemem_online_gate_c_20260803T095434Z_f346d23912a9`

Manifest ID: `08740c5415ad8a95e85fee9f2fe661a7bc791363fd0124ae8a8e1d0478af08ef`

Source commit: `f346d23912a9`

## What happened

After two operational cases, an outer PowerShell process was terminated because
the projected API latency appeared impractical. That termination did **not**
terminate the child Python runner. The immutable runner continued without any
prompt, configuration, seed, threshold, or memory-rule modification and later
completed all 60 operational cases.

This note preserves the operational event but supersedes the earlier incorrect
interpretation that the experiment itself was incomplete. The authoritative
artifacts are now `run_status.json`, which records `COMPLETED`, and
`analysis_summary.json`, which records the failed promotion gate.

## Final interpretation

The run is a complete development experiment, not an incomplete provider
failure. Provider latency remains an important engineering cost: 242 API calls
used about 12.44 million milliseconds of aggregate API time, with 42.6-second
median and 86.8-second p90 latency. However, the scientific reason not to
advance is the failed memory-benefit promotion gate, not latency.
