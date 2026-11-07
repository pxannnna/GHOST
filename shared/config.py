"""Load config/default.json, overlaid by config/local.json if present (ignored by git)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config() -> Dict[str, Any]:
    cfg = json.loads((CONFIG_DIR / "default.json").read_text())
    local = CONFIG_DIR / "local.json"
    if local.exists():
        cfg = _merge(cfg, json.loads(local.read_text()))
    return cfg
