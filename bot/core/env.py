"""Loads bot/.env into os.environ. No external dependencies.
Keeps secrets out of the repo.
"""
import os
from pathlib import Path

# location of the .env file: bot/.env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env():
    if not ENV_PATH.exists():
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and not os.environ.get(key):
                os.environ[key] = value


def get(key, default=""):
    return os.environ.get(key, default)