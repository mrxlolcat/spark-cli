# Route Confidence Read Model V1

Status: design checkpoint for the first release slice.

Owner: `spark-cli`

## Purpose

`spark-cli` should provide the source-owned compiled evidence that Builder needs for `RouteConfidenceGateV1`.

The first card is `LatestSpawnerJobEvidenceV1`, answering:

```text
What is the latest Spawner job, and what provider/model actually executed it?
```

The read model is evidence only. It does not decide actions and does not answer the user by itself.

## Source Inputs

Use metadata-only sources:

- Spawner mission-control rows
- Spawner PRD trace rows
- Spawner `agent-events.jsonl`
- result artifact metadata when already redacted and metadata-only
- registry/runtime source freshness metadata

Do not read or export:

- raw prompt text
- result body or provider output
- chat ids or user ids
- memory bodies
- transcript bodies
- raw audio
- env values
- secrets

## Proposed Shape

```json
{
  "schema_version": "spark.latest_spawner_job_evidence.v1",
  "status": "present",
  "job_kind": "prd_build",
  "mission_id_redacted": "mission:redacted",
  "request_ref_redacted": "request:redacted",
  "trace_ref_redacted": "trace:redacted",
  "provider": "openai",
  "model": "gpt-5.3-codex",
  "provider_source": "agent-events",
  "joined_sources": ["mission-control", "spawner-prd-trace", "agent-events"],
  "missing_sources": [],
  "freshness": "current",
  "confidence": "high",
  "blockers": [],
  "verification_command": "spark os trace --json",
  "data_boundary": {
    "metadata_only": true,
    "raw_payload_exported": false
  }
}
```

## Edge Cases

| Edge case | Compiler behavior |
| --- | --- |
| No mission-control rows | status `missing`, blocker `missing_mission_control` |
| PRD row exists without mission-control join | status `partial`, confidence `low` |
| agent-events provider/model missing | status `partial`, blocker `missing_executed_provider_model` |
| provider appears only in config | record `configured_provider_available` only as non-answer evidence |
| multiple latest candidates tie | status `ambiguous`, blocker `ambiguous_latest_job` |
| latest row is old | freshness `stale`; Builder should not answer as current |
| fixture/test source path | classify as test evidence, not live evidence |
| trace ref exists only nested in facts | project safe redacted trace presence, never raw trace body |
| artifact contains forbidden keys | drop artifact fields and add privacy blocker |
| local/hosted/runtime drift | include runtime source blocker for Builder gate |

## Verification

Initial tests should cover:

- newest-first ordering
- tie/ambiguity handling
- provider config not treated as executed provider
- redaction of request/trace refs
- forbidden payload keys rejected
- metadata-only output

Expected commands:

```powershell
python -m pytest tests/test_system_map.py -q
python -m pytest tests/test_cli.py -q
python -m spark_cli.cli os compile --json
python -m spark_cli.cli os trace --json
```

