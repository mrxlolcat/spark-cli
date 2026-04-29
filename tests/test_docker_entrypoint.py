from __future__ import annotations

from pathlib import Path


def test_live_docker_entrypoint_fails_closed_for_public_spawner() -> None:
    script = (Path(__file__).resolve().parents[1] / "docker" / "live" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "umask 077" in script
    assert "is_public_spawner_bind" in script
    assert "SPARK_ALLOWED_HOSTS is required when Spawner binds publicly" in script
    assert "require_strong_secret SPARK_BRIDGE_API_KEY" in script
    assert "require_strong_secret SPARK_UI_API_KEY" in script
    assert "SPARK_BRIDGE_API_KEY and SPARK_UI_API_KEY must be different" in script
    assert "must contain hostnames only, with no scheme, path, wildcard, or port" in script
