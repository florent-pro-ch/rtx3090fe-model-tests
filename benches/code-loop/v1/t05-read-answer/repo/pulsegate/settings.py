"""Runtime settings for pulsegate.

Resolution order for every value, highest precedence first:

  1. an environment variable listed in ENV_OVERRIDES;
  2. ``config.yaml`` (the file at the repository root, or the path given in
     the PULSEGATE_CONFIG environment variable);
  3. nothing -- a key missing from both is an error, we never guess.

Only the small YAML subset used by config.yaml is understood (nested maps,
scalars, ``#`` comments); there is no third-party dependency.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"

# Location of the config file itself (not a value inside it).
ENV_CONFIG_PATH = "PULSEGATE_CONFIG"

# environment variable -> (section, key, type) inside config.yaml
ENV_OVERRIDES = {
    "PULSEGATE_BIND": ("server", "host", str),
    "PULSEGATE_LISTEN_PORT": ("server", "port", int),
    "PULSEGATE_UPSTREAM": ("upstream", "url", str),
    "PULSEGATE_LOG_LEVEL": ("logging", "level", str),
}


@dataclass(frozen=True)
class Settings:
    service_name: str
    host: str
    port: int
    upstream_url: str
    upstream_timeout: float
    queue_dir: Path
    log_level: str


def _coerce(text: str):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def load_yaml_subset(path: Path) -> dict:
    """Parse nested ``key: value`` maps; comments and blank lines are ignored."""
    root: dict = {}
    stack: list = [(-1, root)]
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value.strip():
            parent[key.strip()] = _coerce(value)
        else:
            child: dict = {}
            parent[key.strip()] = child
            stack.append((indent, child))
    return root


def load_settings(config_path=None, environ: Mapping[str, str] | None = None) -> Settings:
    """Build Settings from config.yaml, then apply the environment overrides."""
    env = os.environ if environ is None else environ
    path = Path(config_path or env.get(ENV_CONFIG_PATH) or DEFAULT_CONFIG_PATH)
    data = load_yaml_subset(path)
    for name, (section, key, cast) in ENV_OVERRIDES.items():
        if name in env:
            data.setdefault(section, {})[key] = cast(env[name])
    try:
        return Settings(
            service_name=str(data["service"]["name"]),
            host=str(data["server"]["host"]),
            port=int(data["server"]["port"]),
            upstream_url=str(data["upstream"]["url"]),
            upstream_timeout=float(data["upstream"]["timeout_seconds"]),
            queue_dir=REPO_ROOT / str(data["queue"]["dir"]),
            log_level=str(data["logging"]["level"]),
        )
    except KeyError as exc:
        raise KeyError(f"{path}: missing setting {exc}") from exc
