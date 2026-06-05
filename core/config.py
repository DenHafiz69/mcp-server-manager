import os
import json
import platform
from pathlib import Path

MASTER_CONFIG_PATH = os.path.expanduser("~/.mcp-manager.json")

def get_claude_config_path() -> Path:
    if platform.system() == "Darwin":
        return Path(os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json"))
    elif platform.system() == "Windows":
        return Path(os.path.expandvars("%APPDATA%\\Claude\\claude_desktop_config.json"))
    else:
        return Path(os.path.expanduser("~/.config/Claude/claude_desktop_config.json"))

def get_cursor_config_path() -> Path:
    return Path(os.path.expanduser("~/.cursor/mcp.json"))

class ConfigManager:
    @staticmethod
    def load_master_config() -> dict:
        if not os.path.exists(MASTER_CONFIG_PATH):
            return {"mcpServers": {}}
        try:
            with open(MASTER_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"mcpServers": {}}

    @staticmethod
    def save_master_config(config: dict):
        with open(MASTER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    @staticmethod
    def sync_to_apps(config: dict):
        active_servers = {}
        for name, details in config.get("mcpServers", {}).items():
            if details.get("enabled", False):
                # Copy details without the 'enabled' key
                server_config = {k: v for k, v in details.items() if k != "enabled"}
                active_servers[name] = server_config

        ConfigManager._sync_target(get_claude_config_path(), active_servers)
        ConfigManager._sync_target(get_cursor_config_path(), active_servers)

    @staticmethod
    def _sync_target(target_path: Path, active_servers: dict):
        target_path.parent.mkdir(parents=True, exist_ok=True)

        existing_config = {}
        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            except Exception:
                existing_config = {}

        if "mcpServers" not in existing_config:
            existing_config["mcpServers"] = {}

        existing_config["mcpServers"] = active_servers

        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=2)
        except Exception:
            pass
