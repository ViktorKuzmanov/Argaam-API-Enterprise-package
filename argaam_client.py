"""Small Argaam API client: GET a path, save the JSON response under data/<api>/.

Used by the web app for one request at a time. Bulk downloads (many keys, proxy,
retries, resume) live in argaam_downloader.py.
"""
import json
import os
import re
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("ARGAAM_API_BASE", "https://api-sandbox.argaam.com/api/v1.1").rstrip("/")
API_KEY = os.getenv("ARGAAM_SANDBOX_API_KEY", "")
DATA_DIR = Path(__file__).parent / "data"
# One folder per API, so each API's saved responses stay together.
MACRO_DIR = DATA_DIR / "macroeconomic"       # /indicators/... (macroeconomic API)
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"  # /companies/..., /markets/... (fundamentals API)


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
    if resp.status_code == 204 or not resp.content.strip():
        raise LookupError(
            f"No data returned (HTTP {resp.status_code}) for {path}. "
            "The ID may not exist, or there is no data for it (common in the sandbox). "
            "List a group's valid fields with /indicators/groups/{groupId}/fields."
        )
    try:
        return resp.json()
    except ValueError:
        ctype = resp.headers.get("content-type", "unknown")
        raise ValueError(
            f"Response is not JSON (HTTP {resp.status_code}, {ctype}): {resp.text[:300]}"
        ) from None


def file_for(name, folder):
    """Return the path inside folder (e.g. MACRO_DIR) a response called name is saved under."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "response"
    return folder / f"{safe}.json"


def write_json(path, data):
    """Write through a temp file so a crash can never leave half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save(data, name, folder):
    """Write data to <folder>/<name>.json and return the file path."""
    path = file_for(name, folder)
    write_json(path, data)
    return path


def fetch_and_save(path, folder, name=None, base=None, params=None):
    data = fetch(path, base=base, params=params)
    file = save(data, name or path, folder)
    return data, file


def saved_name(file):
    """Path of a saved file relative to data/, e.g. macroeconomic/indicator_groups.json."""
    return file.relative_to(DATA_DIR).as_posix()
