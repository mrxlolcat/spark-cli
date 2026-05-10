from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from .capabilities import CapabilityManifest


def docker_capabilities() -> CapabilityManifest:
    return CapabilityManifest(
        backend="docker",
        filesystem="workspace",
        network="off",
        secrets="none",
        persistence="ephemeral",
        privilege="container",
        inbound="none",
        cost="local",
    )


def docker_os_family(platform: str | None = None) -> str:
    value = platform or sys.platform
    if value == "darwin":
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    return "unknown"


def docker_repair_hint(family: str) -> str:
    if family == "macos":
        return "Install Docker Desktop for Mac, then rerun `spark sandbox docker doctor`."
    if family == "windows":
        return "Install Docker Desktop for Windows with WSL support, then rerun `spark sandbox docker doctor`."
    if family == "linux":
        return "Install Docker Engine or Docker Desktop for your Linux distro, then rerun `spark sandbox docker doctor`."
    return "Install Docker for this operating system, then rerun `spark sandbox docker doctor`."


def _check(name: str, ok: bool, detail: str, *, repair: str = "", level: str | None = None) -> dict[str, object]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "repair": repair,
        "level": level or ("info" if ok else "error"),
    }


def collect_docker_doctor_payload(*, timeout: int = 8) -> dict[str, Any]:
    family = docker_os_family()
    docker_path = shutil.which("docker")
    checks = [
        _check(
            "docker_cli",
            bool(docker_path),
            f"Docker CLI found at {docker_path}." if docker_path else "Docker CLI was not found on PATH.",
            repair=docker_repair_hint(family),
        )
    ]
    daemon_ok = False
    version_detail = "Docker daemon was not checked because the CLI is missing."
    if docker_path:
        try:
            result = subprocess.run(
                [docker_path, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            daemon_ok = result.returncode == 0 and bool((result.stdout or "").strip())
            version_detail = (
                f"Docker daemon responded with server version {(result.stdout or '').strip()}."
                if daemon_ok
                else "Docker CLI is installed, but the daemon is not responding."
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            version_detail = f"Docker daemon check failed: {error.__class__.__name__}."
    checks.append(
        _check(
            "docker_daemon",
            daemon_ok,
            version_detail,
            repair="Start Docker Desktop or the Docker service, then rerun `spark sandbox docker doctor`.",
        )
    )
    checks.append(
        _check(
            "spark_policy",
            True,
            "Spark Docker lane is optional and should only mount approved Spark workspaces.",
        )
    )
    ok = all(bool(check["ok"]) for check in checks if check.get("level") != "warning")
    return {
        "ok": ok,
        "backend": "docker",
        "command": "doctor",
        "os_family": family,
        "capabilities": docker_capabilities().to_dict(),
        "checks": checks,
        "next": "Run `spark access setup --with docker` for Docker-backed Level 4 tasks." if ok else docker_repair_hint(family),
    }

