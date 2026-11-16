"""
Configuration loader for TARS robot.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    target = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not target.exists():
        # Fallback to local config.json in working dir
        target = Path("config.json")
    
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Config] Error loading {target}: {e}")
    
    return {}
