import json
import os
import tempfile
from typing import Any, Dict

CONFIG_FILENAME = "pid_tags_config.json"


def get_config_path() -> str:
    return os.path.join(tempfile.gettempdir(), CONFIG_FILENAME)


def load_settings() -> Dict[str, Any]:
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            # Fall back to defaults if the file is malformed
            pass

    return {
        "provider": "azure",  # or "openai"
        "api_key": "",
        "endpoint_url": "",
        "deployment": "",
        "api_version": "",
        "model": "gpt-4.1",
    }


def save_settings(settings: Dict[str, Any]) -> str:
    """Persist settings locally in a temp file. File is not encrypted."""
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        # Best-effort; platform may not support chmod in all environments
        pass
    return path
