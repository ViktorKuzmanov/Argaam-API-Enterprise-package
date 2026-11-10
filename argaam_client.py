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


# ---- Endpoints and file names -------------------------------------------------------------------
# static/endpoints.json is the one list of endpoints, read by Python and by the page. Each entry says
# which API it belongs to (the folder under data/), its Argaam path, which values go in the query
# string, and its "file" template: where a response is saved inside data/<api>/.
# Example: analyst_estimates with marketId=3, symbol=2222, period=year
#          -> GET /companies/2222/analyst-estimates?marketId=3&period=year
#          -> data/fundamentals/analyst_estimates/3_2222_year.json

ENDPOINTS = {e["id"]: e for e in json.loads((Path(__file__).parent / "static" / "endpoints.json").read_text(encoding="utf-8"))}
VALUE = r"[A-Za-z0-9-]+"  # allowed in a filled-in value; no "_" or "/", so file names stay unambiguous


def check_values(endpoint_id, values):
    ep = ENDPOINTS[endpoint_id]
    needed = set(re.findall(r"\{(\w+)\}", ep["path"] + ep["file"])) | set(ep.get("query", []))
    if set(values) != needed:
        raise ValueError(f"{endpoint_id} needs {sorted(needed)}, got {sorted(values)}")
    for name, value in values.items():
        if not re.fullmatch(VALUE, str(value)):
            raise ValueError(f"{name} must be letters, digits or '-', got {value!r}")


def item_name(endpoint_id, **values):
    """The file template filled in, e.g. analyst_estimates/3_2222_year. Also the key in _progress.json."""
    check_values(endpoint_id, values)
    return ENDPOINTS[endpoint_id]["file"].format(**values)


def saved_file(endpoint_id, **values):
    """Where this endpoint's response for these values is saved, e.g. data/fundamentals/analyst_estimates/3_2222_year.json."""
    return DATA_DIR / ENDPOINTS[endpoint_id]["api"] / f"{item_name(endpoint_id, **values)}.json"


def api_request(endpoint_id, **values):
    """The Argaam path and query parameters for these values."""
    check_values(endpoint_id, values)
    ep = ENDPOINTS[endpoint_id]
    return ep["path"].format(**values), {k: values[k] for k in ep.get("query", [])}


def match_path(path, api):
    """Which endpoint of this API a typed path belongs to: returns (endpoint_id, values), or None."""
    for ep in ENDPOINTS.values():
        if ep["api"] != api or ep.get("query"):
            continue
        parts = re.split(r"\{(\w+)\}", ep["path"])  # literal, name, literal, name, ...
        pattern = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>{VALUE})" for i, p in enumerate(parts))
        m = re.fullmatch(pattern, path.strip().rstrip("/") or "/")
        if m:
            return ep["id"], m.groupdict()
    return None


def write_json(path, data):
    """Write through a temp file so a crash can never leave half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def fetch_and_save(endpoint_id, base=None, **values):
    """Fetch one endpoint for these values and save it where saved_file() says. Returns (data, file)."""
    path, params = api_request(endpoint_id, **values)
    data = fetch(path, base=base, params=params or None)
    file = saved_file(endpoint_id, **values)
    write_json(file, data)
    return data, file


def saved_name(file):
    """Path of a saved file relative to data/, e.g. macroeconomic/indicator_groups.json."""
    return file.relative_to(DATA_DIR).as_posix()
