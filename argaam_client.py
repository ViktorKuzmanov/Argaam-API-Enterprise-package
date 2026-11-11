"""Shared Argaam basics, used by the web app and by every fetch script.

  - Endpoints and file names: static/endpoints.json says where every response is saved.
  - Bookkeeping: key usage (.fetch_state/key_usage.json) and per-API progress (data/<api>/_progress.json).
  - Single requests for the app: fetch() and fetch_and_save(), which also do the bookkeeping.

Bulk downloads (many keys, proxy, pacing, retries, resume) live in argaam_downloader.py.
"""
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def write_json(path, data):
    """Write through a temp file so a crash can never leave half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def saved_name(file):
    """Path of a saved file relative to data/, e.g. macroeconomic/indicator_groups.json."""
    return file.relative_to(DATA_DIR).as_posix()


# ---- Bookkeeping, shared by the app and every fetch script --------------------------------------
# .fetch_state/key_usage.json  calls each API key used today. Not committed: it lives outside data/,
#                              because everything in data/ is published to GitHub Pages.
# data/<api>/_progress.json    what happened to each item and where it came from. Committed.
# Both files are re-read before every write, so the app and a fetch script running at the same
# time do not undo each other's updates.

STATE_DIR = Path(__file__).parent / ".fetch_state"
USAGE_FILE = STATE_DIR / "key_usage.json"
lock = threading.Lock()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(key):
    """First 8 characters of the key's SHA-256 hash: tells keys apart, but cannot be turned back into the key.
    Counts stay with the right key even if the order of ARGAAM_API_KEYS in .env changes."""
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def used_from_headers(resp):
    """Calls this key used today according to Argaam's headers, or None when they are missing."""
    left, limit = resp.headers.get("X-RateLimit-Remaining-Day"), resp.headers.get("X-RateLimit-Limit-Day")
    return int(limit) - int(left) if left is not None and limit is not None else None


class KeyUsage:
    """Calls each API key used today, per endpoint: Argaam's daily limit (100) counts each endpoint separately,
    so one key can make 100 indicator_values calls and still 100 fund_history calls on the same day.
    Stored as {"2026-11-10": {"<fingerprint>": {"indicator_values": 39, ...}, ...}}; only today (UTC) is kept."""

    def __init__(self, path=None):
        self.path = path or USAGE_FILE
        self.counts = self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            data = {}
        # Older files had one number per key; those counts cannot be split by endpoint, so they are dropped.
        return {fp: per for fp, per in data.get(today(), {}).items() if isinstance(per, dict)}

    def used(self, fp, endpoint):
        return self.counts.get(fp, {}).get(endpoint, 0)

    def record(self, fp, endpoint, used=None):
        """Set this key's count for this endpoint to used (from Argaam's headers), or add 1 when they are missing."""
        with lock:
            self.counts = self.load()
            per = self.counts.setdefault(fp, {})
            per[endpoint] = used if used is not None else per.get(endpoint, 0) + 1
            write_json(self.path, {today(): self.counts})


@dataclass
class Task:
    """One request to make: GET path with params, and save the response to file."""
    name: str    # the key in _progress.json and in the log, e.g. analyst_estimates/3_2222_year
    path: str    # API path, e.g. /companies/2222/analyst-estimates
    file: Path   # where the response is saved
    params: dict = field(default_factory=dict)
    endpoint: str = ""  # endpoint id, e.g. analyst_estimates: Argaam's daily limit is counted per endpoint
    attempts: int = 0


def endpoint_task(endpoint_id, **values):
    """A Task for one endpoint in static/endpoints.json: its path, query, file and name all come from there."""
    path, params = api_request(endpoint_id, **values)
    return Task(name=item_name(endpoint_id, **values), path=path, file=saved_file(endpoint_id, **values),
                params=params, endpoint=endpoint_id)


class Progress:
    """One API's progress file, data/<api>/_progress.json.

    One entry per item, keyed by the task name: status (saved, no_data or failed) plus where it came from
    (base, path, params) and when. Saved and no_data items are skipped on the next run; failed ones are retried.
    """

    def __init__(self, folder):
        self.api = folder.name
        self.path = folder / "_progress.json"
        self.items = self.load()

    def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("items", {})
        except FileNotFoundError:
            return {}

    def status(self, name):
        return self.items.get(name, {}).get("status")

    def is_done(self, name):
        return self.status(name) in ("saved", "no_data")

    def record(self, task, status, base=None, **extra):
        entry = {"status": status}
        if status == "saved":
            entry["file"] = task.file.relative_to(DATA_DIR).as_posix()
        entry.update(base=base or API_BASE, path=task.path, params=task.params, fetched_at=now(), **extra)
        with lock:
            self.items = self.load()  # pick up what the app or another script recorded meanwhile
            if status == "failed" and self.is_done(task.name):
                return  # keep what an earlier run saved; a failed --refresh does not undo it
            self.items[task.name] = entry
            write_json(self.path, {"api": self.api, "items": dict(sorted(self.items.items()))})


def progress_for(endpoint_id):
    return Progress(DATA_DIR / ENDPOINTS[endpoint_id]["api"])


def known_no_data(endpoint_id, **values):
    """The progress entry if Argaam is already recorded as having no data for this, else None."""
    entry = progress_for(endpoint_id).items.get(item_name(endpoint_id, **values))
    return entry if entry and entry["status"] == "no_data" else None


# ---- Single requests, used by the app -----------------------------------------------------------

class NoData(LookupError):
    """Argaam answered, but had no data for this request (HTTP 204 or an empty body)."""

    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def fetch(path, base=None, params=None, endpoint="other"):
    """GET {base}{path} with the apikey header, count the call in key_usage.json under this endpoint id,
    and return the parsed JSON."""
    if not API_KEY or API_KEY == "your_sandbox_api_key_here":
        raise RuntimeError("Set ARGAAM_SANDBOX_API_KEY in .env")
    url = (base or API_BASE).rstrip("/") + "/" + path.lstrip("/")
    resp = requests.get(
        url,
        headers={"Accept": "application/json", "apikey": API_KEY},
        params=params,
        timeout=30,
    )
    KeyUsage().record(fingerprint(API_KEY), endpoint, used_from_headers(resp))
    resp.raise_for_status()
    if resp.status_code == 204 or not resp.content.strip():
        raise NoData(
            f"No data returned (HTTP {resp.status_code}) for {path}. "
            "The ID may not exist, or there is no data for it (common in the sandbox). "
            "List a group's valid fields with /indicators/groups/{groupId}/fields.",
            resp.status_code,
        )
    try:
        return resp.json()
    except ValueError:
        ctype = resp.headers.get("content-type", "unknown")
        raise ValueError(
            f"Response is not JSON (HTTP {resp.status_code}, {ctype}): {resp.text[:300]}"
        ) from None


def fetch_and_save(endpoint_id, base=None, **values):
    """Fetch one endpoint for these values, save it where saved_file() says, and record the result
    in data/<api>/_progress.json, the same way the fetch scripts do. Returns (data, file)."""
    task = endpoint_task(endpoint_id, **values)
    progress = progress_for(endpoint_id)
    base = (base or API_BASE).rstrip("/")
    try:
        data = fetch(task.path, base=base, params=task.params or None, endpoint=endpoint_id)
    except NoData as e:
        progress.record(task, "no_data", base=base, http=e.status)
        raise
    except requests.HTTPError as e:
        code = e.response.status_code
        if code == 404:
            progress.record(task, "no_data", base=base, http=404)
        elif code not in (401, 403, 429):  # a key or rate-limit problem is not the item's fault
            progress.record(task, "failed", base=base, reason=f"HTTP {code}")
        raise
    write_json(task.file, data)
    progress.record(task, "saved", base=base)
    return data, task.file
