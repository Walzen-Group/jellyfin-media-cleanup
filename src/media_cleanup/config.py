"""
Application configuration.

Loads credentials and settings from secrets.yaml and/or environment variables.
Env vars take precedence over file values.
"""

import os
import yaml
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MONTH_THRESHOLD = 6

# Default secrets.yaml location: project root (two levels up from src/media_cleanup/)
_DEFAULT_SECRETS_PATH = Path(__file__).resolve().parent.parent.parent / "secrets.yaml"


@dataclass
class AppConfig:
    """All configuration needed to run the media cleanup pipeline."""
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    month_threshold: int = DEFAULT_MONTH_THRESHOLD
    db_path: Path = Path("cleanup_history.db")


def load_config(path: Path | None = None) -> AppConfig:
    """
    Build an AppConfig from secrets.yaml (if provided and exists) overlaid
    with environment variables.

    Env vars checked:
        JELLYFIN_URL, JELLYFIN_API_KEY,
        SONARR_URL, SONARR_API_KEY,
        RADARR_URL, RADARR_API_KEY,
        MONTH_THRESHOLD
    """
    # Fall back to default secrets.yaml location if no path given
    if path is None:
        path = _DEFAULT_SECRETS_PATH

    file_cfg: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}

    def _get(env_key: str, *yaml_keys: str, default: str = "") -> str:
        """Return env var if set, else dig into file_cfg, else default."""
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
        obj = file_cfg
        for k in yaml_keys:
            if isinstance(obj, dict):
                obj = obj.get(k, {})
            else:
                return default
        return obj if isinstance(obj, str) else default

    month_env = os.environ.get("MONTH_THRESHOLD")
    month_file = (file_cfg.get("settings") or {}).get("month_threshold")

    if month_env is not None:
        month_threshold = int(month_env)
    elif month_file is not None:
        month_threshold = int(month_file)
    else:
        month_threshold = DEFAULT_MONTH_THRESHOLD

    db_path_env = os.environ.get("CLEANUP_DB_PATH")
    db_path = Path(db_path_env) if db_path_env else Path("cleanup_history.db")

    return AppConfig(
        jellyfin_url=_get("JELLYFIN_URL", "jellyfin", "url"),
        jellyfin_api_key=_get("JELLYFIN_API_KEY", "jellyfin", "api_key"),
        sonarr_url=_get("SONARR_URL", "sonarr", "url"),
        sonarr_api_key=_get("SONARR_API_KEY", "sonarr", "api_key"),
        radarr_url=_get("RADARR_URL", "radarr", "url"),
        radarr_api_key=_get("RADARR_API_KEY", "radarr", "api_key"),
        month_threshold=month_threshold,
        db_path=db_path,
    )
