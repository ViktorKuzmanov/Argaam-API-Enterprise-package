"""Small Argaam API client: GET a path, save the JSON response to data/."""
import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("ARGAAM_API_BASE", "https://api-sandbox.argaam.com/api/v1.1").rstrip("/")
API_KEY = os.getenv("ARGAAM_SANDBOX_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"


def fetch(path, base=None, params=None):
    """GET {base}{path} with the apikey header and return the parsed JSON."""
    if not API_KEY or API_KEY == "your_sandbox_api_key_here":
        raise RuntimeError("Set ARGAAM_SANDBOX_API_KEY in .env")
    url = (base or API_BASE).rstrip("/") + "/" + path.lstrip("/")
    resp = requests.get(
        url,
        headers={"Accept": "application/json", "apikey": API_KEY},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def save(data, name):
    """Write data to data/<name>.json and return the file path."""
    DATA_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "response"
    path = DATA_DIR / f"{safe}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fetch_and_save(path, name=None, base=None, params=None):
    data = fetch(path, base=base, params=params)
    file = save(data, name or path)
    return data, file

