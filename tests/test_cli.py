from __future__ import annotations

import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import (
    build_module_envs,
    collect_secret_requirements,
    collect_secret_values,
    Module,
    MODULE_CONFIG_DIR,
    detect_capability_conflicts,
    detect_ingress_owner,
    expand_targets,
    generated_module_env_path,
    remove_managed_env_block,
    print_install_summary,
    resolve_bundle_names,
    resolve_install_target,
    summarize_command_output,
    update_setup_state_after_uninstall,
    update_env_file,
    CONFIG_PATH,
)


def make_module(name: str, capabilities: list[str]) -> Module:
    return Module(
        name=name,
        path=Path(f"C:/tmp/{name}"),
        manifest={
            "module": {
                "name": name,
                "version": "0.1.0",
                "kind": "service",
                "plane": "ingress",
            },
            "provides": {
                "capabilities": capabilities,
            },
        },
    )


class SparkCliTests(unittest.TestCase):
    def test_detect_ingress_owner_returns_single_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        owner = detect_ingress_owner([gateway, runtime])
        self.assertEqual(owner.name, "spark-telegram-bot")

    def test_expand_targets_expands_bundle_name(self) -> None:
        modules = {
            "spark-telegram-bot": object(),
            "spark-intelligence-builder": object(),
            "spawner-ui": object(),
        }
        self.assertEqual(
            expand_targets("telegram-starter", modules, include_all=False),
            ["spark-telegram-bot", "spark-intelligence-builder", "spawner-ui"],
        )

    def test_summarize_command_output_skips_npm_prefix_lines(self) -> None:
        result = subprocess.CompletedProcess(
            args=["dummy"],
            returncode=1,
            stdout="> spawner-ui@0.0.1 health:spark\n> node scripts/health-spark.mjs\nSpawner UI unhealthy: cannot reach http://127.0.0.1:5173/api/providers\n",
            stderr="",
        )
        self.assertEqual(
            summarize_command_output(result),
            "Spawner UI unhealthy: cannot reach http://127.0.0.1:5173/api/providers",
        )

    def test_update_env_file_replaces_managed_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text("EXISTING=1\n# --- spark-cli managed start ---\nOLD=1\n# --- spark-cli managed end ---\n", encoding="utf-8")

            update_env_file(env_path, {"BOT_TOKEN": "abc", "ADMIN_TELEGRAM_IDS": "123"})
            contents = env_path.read_text(encoding="utf-8")

            self.assertIn("EXISTING=1", contents)
            self.assertIn("BOT_TOKEN=abc", contents)
            self.assertIn("ADMIN_TELEGRAM_IDS=123", contents)
            self.assertNotIn("OLD=1", contents)

    def test_resolve_install_target_prefers_registry_module_name(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        resolved = resolve_install_target("spark-telegram-bot", {"spark-telegram-bot": gateway})
        self.assertEqual(resolved.name, "spark-telegram-bot")

    def test_resolve_install_target_accepts_local_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir) / "module"
            repo_path.mkdir()
            (repo_path / "spark.toml").write_text(
                '[module]\nname = "test-module"\nversion = "0.1.0"\nkind = "service"\nplane = "execution"\n',
                encoding="utf-8",
            )
            resolved = resolve_install_target(str(repo_path), {})
            self.assertEqual(resolved.name, "test-module")

    def test_resolve_bundle_names_reads_registry_bundle(self) -> None:
        self.assertEqual(
            resolve_bundle_names("telegram-starter"),
            ["spark-telegram-bot", "spark-intelligence-builder", "spawner-ui"],
        )

    def test_print_install_summary_mentions_ingress_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        with patch("sys.stdout", new_callable=StringIO) as stdout:
            print_install_summary([gateway, runtime])
            output = stdout.getvalue()
        self.assertIn("Install plan:", output)
        self.assertIn("Telegram ingress owner: spark-telegram-bot", output)

    def test_detect_capability_conflicts_allows_single_ingress_owner(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        runtime = make_module("spark-intelligence-builder", ["spark.runtime"])
        self.assertEqual(detect_capability_conflicts([gateway, runtime], {}), [])

    def test_detect_capability_conflicts_rejects_multiple_ingress_owners(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        other_gateway = make_module("other-telegram-gateway", ["telegram.ingress"])
        conflicts = detect_capability_conflicts([gateway, other_gateway], {})
        self.assertEqual(
            conflicts,
            ["multiple telegram ingress owners declared: other-telegram-gateway, spark-telegram-bot"],
        )

    def test_collect_secret_requirements_maps_manifest_secret_blocks(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token", "telegram.admin_ids"]},
                "secrets": {
                    "telegram_bot_token": {"prompt": "Bot token", "required": True, "env_var": "BOT_TOKEN"},
                    "telegram_admin_ids": {"prompt": "Admin ids", "required": True, "env_var": "ADMIN_TELEGRAM_IDS"},
                },
            },
        )
        requirements = collect_secret_requirements([module])
        self.assertEqual(requirements["telegram.bot_token"]["env_var"], "BOT_TOKEN")
        self.assertEqual(requirements["telegram.admin_ids"]["env_var"], "ADMIN_TELEGRAM_IDS")

    def test_collect_secret_values_accepts_generic_secret_flags(self) -> None:
        module = Module(
            name="spark-telegram-bot",
            path=Path("C:/tmp/spark-telegram-bot"),
            manifest={
                "module": {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "service", "plane": "ingress"},
                "needs": {"secrets": ["telegram.bot_token"]},
                "secrets": {
                    "telegram_bot_token": {"prompt": "Bot token", "required": True, "env_var": "BOT_TOKEN"},
                },
            },
        )

        class Args:
            secret = ["telegram.bot_token=abc"]
            bot_token = None
            admin_telegram_ids = None
            telegram_webhook_secret = None

        values = collect_secret_values(Args(), [module])
        self.assertEqual(values["telegram.bot_token"], "abc")

    def test_generated_module_env_path_uses_canonical_module_config_dir(self) -> None:
        module = make_module("spawner-ui", ["mission.execution"])
        self.assertEqual(generated_module_env_path(module), MODULE_CONFIG_DIR / "spawner-ui.env")

    def test_build_module_envs_routes_telegram_secret_only_to_gateway(self) -> None:
        gateway = make_module("spark-telegram-bot", ["telegram.ingress"])
        builder = make_module("spark-intelligence-builder", ["spark.runtime"])
        spawner = make_module("spawner-ui", ["mission.execution"])

        class Args:
            spawner_ui_url = "http://127.0.0.1:5173"
            telegram_gateway_mode = "auto"
            telegram_webhook_url = None

        envs = build_module_envs(
            Args(),
            {
                gateway.name: gateway,
                builder.name: builder,
                spawner.name: spawner,
            },
            {
                "telegram.bot_token": "abc",
                "telegram.admin_ids": "123",
                "telegram.webhook_secret": "secret",
            },
        )
        self.assertEqual(envs["spark-telegram-bot"]["BOT_TOKEN"], "abc")
        self.assertNotIn("BOT_TOKEN", envs["spawner-ui"])

    def test_remove_managed_env_block_strips_only_managed_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "KEEP=1\n# --- spark-cli managed start ---\nBOT_TOKEN=abc\n# --- spark-cli managed end ---\n",
                encoding="utf-8",
            )
            remove_managed_env_block(env_path)
            self.assertEqual(env_path.read_text(encoding="utf-8"), "KEEP=1\n")

    def test_update_setup_state_after_uninstall_clears_empty_setup(self) -> None:
        original = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                '{\n  "modules": ["spark-telegram-bot"],\n  "telegram_ingress_owner": "spark-telegram-bot"\n}\n',
                encoding="utf-8",
            )
            update_setup_state_after_uninstall(["spark-telegram-bot"])
            self.assertFalse(CONFIG_PATH.exists())
        finally:
            if original is not None:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_PATH.write_text(original, encoding="utf-8")
            elif CONFIG_PATH.exists():
                CONFIG_PATH.unlink()


if __name__ == "__main__":
    unittest.main()
