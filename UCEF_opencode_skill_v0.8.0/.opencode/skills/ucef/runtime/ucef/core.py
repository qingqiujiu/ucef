from pathlib import Path
import yaml


def load_yaml(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data or {}


def load_runtime_config(path="config.yaml"):
    return load_yaml(path)


import hashlib
import json
import re


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(obj, ignored_keys=None):
    ignored_keys = ignored_keys or set()
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k not in ignored_keys}
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def approx_tokens(text, chars_per_token=4):
    return max(1, len(text) // max(1, chars_per_token)) if text else 0


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
