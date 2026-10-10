"""Load config.yaml (falls back to config.example.yaml) and resolve secrets from the environment."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    candidates = [Path(path)] if path else [ROOT / "config.yaml", ROOT / "config.example.yaml"]
    for p in candidates:
        if p.exists():
            cfg = yaml.safe_load(p.read_text()) or {}
            cfg["_path"] = str(p)
            return cfg
    raise FileNotFoundError("No config.yaml found. Copy config.example.yaml to config.yaml.")


def secret(name: str) -> str | None:
    """Secrets live in environment variables only, never in config files."""
    return os.environ.get(name) or None


def resolve(cfg: dict, key: str, default: str) -> Path:
    p = Path(cfg.get("paths", {}).get(key, default))
    return p if p.is_absolute() else ROOT / p
