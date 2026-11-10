"""Bulk downloader shared by every fetch_*.py script.

A fetch script only decides WHAT to fetch (a list of Task objects). This file decides
HOW: each key in ARGAAM_API_KEYS gets its own worker thread, HTTP session and Data
Impulse exit IP, requests are paced and retried, rate limits are respected, and every
response is written to disk as soon as it arrives, so a stopped run can resume.

The web app does not use this file; it uses the single-request helpers in argaam_client.py.
"""
import json
import os
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from argaam_client import API_BASE, write_json  # also loads .env

KEYS = [k.strip() for k in os.getenv("ARGAAM_API_KEYS", "").split(",") if k.strip()]
DAILY_LIMIT = int(os.getenv("ARGAAM_DAILY_LIMIT_PER_KEY", "100"))
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "45"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "4"))
DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "13"))
DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "18"))

PROXY_LOGIN = os.getenv("DATA_IMPULSE_LOGIN", "")
PROXY_PASSWORD = os.getenv("DATA_IMPULSE_PASSWORD", "")
PROXY_HOST = os.getenv("DATA_IMPULSE_PROXY_HOST", "gw.dataimpulse.com")
PROXY_PORT = os.getenv("DATA_IMPULSE_PROXY_PORT", "823")
PROXY_COUNTRY = os.getenv("DATA_IMPULSE_PROXY_COUNTRY", "")

MAX_CONSECUTIVE_429 = 5

# Progress files live here, outside data/, because everything in data/ is published to GitHub Pages.
STATE_DIR = Path(__file__).parent / ".fetch_state"

lock = threading.Lock()
stop = threading.Event()


def log(message):
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class FetchState:
    """A script's progress file: items that had no data, and calls each key used today."""

    def __init__(self, path):
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.setdefault("no_data", {})
        data.setdefault("usage", {})
        data["usage"] = {today(): data["usage"].get(today(), {})}
        self.data = data

    @property
    def no_data(self):
        return self.data["no_data"]

    def today_usage(self):
        return self.data["usage"].setdefault(today(), {})

    def used(self, label):
        return self.today_usage().get(label, 0)

    def save(self):
        """Call while holding the lock."""
        write_json(self.path, self.data)


@dataclass
class Task:
    """One request to make: GET path with params, and save the response to file."""
    name: str    # shown in the log and used as the key in the progress file
    path: str    # API path, e.g. /companies/2222/analyst-estimates
    file: Path   # where the response is saved
    params: dict = field(default_factory=dict)
    attempts: int = 0


class Slot:
    """One API key with its own HTTP session, proxy IP and pacing."""

    def __init__(self, index, key, state):
        self.label = f"key{index + 1:02d}"
        self.index = index
        self.key = key
        self.state = state
        self.rotation = 0
        self.next_at = time.monotonic() + random.uniform(0, DELAY_MAX)
        self.retired = None
        self.consecutive_429 = 0
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"Accept": "application/json", "apikey": key})
        self.apply_proxy()

    def apply_proxy(self):
        session_id = f"argaam{self.index}r{self.rotation}"
        country = f"cr.{PROXY_COUNTRY};" if PROXY_COUNTRY else ""
        login = quote(f"{PROXY_LOGIN}__{country}sessid.{session_id}", safe="")
        url = f"http://{login}:{quote(PROXY_PASSWORD, safe='')}@{PROXY_HOST}:{PROXY_PORT}"
        self.session.proxies = {"http": url, "https": url}

    def new_ip(self):
        self.rotation += 1
        self.session.close()
        self.apply_proxy()

    @property
    def used(self):
        return self.state.used(self.label)

    def retire(self, reason):
        if not self.retired:
            self.retired = reason
            log(f"{self.label} stopped for this run: {reason}")

    def get(self, url, params=None):
        """Wait for this key's turn, send one request and record the quota it used."""
        pause = self.next_at - time.monotonic()
        if pause > 0 and stop.wait(pause):
            return None
        self.next_at = time.monotonic() + random.uniform(DELAY_MIN, DELAY_MAX)
        resp = self.session.get(url, params=params, timeout=TIMEOUT)
        self.record_quota(resp)
        return resp

    def record_quota(self, resp):
        day_left = resp.headers.get("X-RateLimit-Remaining-Day")
        day_limit = resp.headers.get("X-RateLimit-Limit-Day")
        with lock:
            usage = self.state.today_usage()
            if day_left is not None and day_limit is not None:
                usage[self.label] = int(day_limit) - int(day_left)
            else:
                usage[self.label] = usage.get(self.label, 0) + 1
            self.state.save()
        if day_left is not None and int(day_left) <= 0:
            self.retire("daily limit reached")
        elif resp.headers.get("X-RateLimit-Remaining-Minute") == "0":
            self.cool_down(resp)

    def cool_down(self, resp):
        wait = resp.headers.get("Retry-After") or resp.headers.get("RateLimit-Reset") or "60"
        seconds = float(wait) if wait.replace(".", "", 1).isdigit() else 60
        self.next_at = max(self.next_at, time.monotonic() + seconds + 1)


def make_slots(state):
    """One Slot per key in ARGAAM_API_KEYS. Stops the script if keys or proxy login are missing."""
    if not KEYS:
        raise SystemExit("Set ARGAAM_API_KEYS in .env (comma separated).")
    if not (PROXY_LOGIN and PROXY_PASSWORD):
        raise SystemExit("Set DATA_IMPULSE_LOGIN and DATA_IMPULSE_PASSWORD in .env.")
    return [Slot(i, key, state) for i, key in enumerate(KEYS)]


def calls_left(slots):
    """Calls all keys together may still make today."""
    return sum(max(0, DAILY_LIMIT - s.used) for s in slots)


def fetch_one(slots, path, what, params=None):
    """Fetch a single response (e.g. a list to discover what to fetch next), trying each key in turn."""
    url = f"{API_BASE}{path}"
    for slot in slots:
        if slot.used >= DAILY_LIMIT:
            continue
        try:
            resp = slot.get(url, params)
        except requests.RequestException as e:
            log(f"{slot.label} could not get {what}: {type(e).__name__}")
            slot.new_ip()
            continue
        if resp is not None and resp.status_code == 200:
            return resp.json()
        if resp is not None:
            log(f"{slot.label} {what}: HTTP {resp.status_code}")
    raise SystemExit(f"Could not download {what}.")


class Run:
    """Works through a queue of Tasks with one worker per key."""

    def __init__(self, tasks, state, count_rows=None):
        self.tasks = queue.Queue()
        for task in tasks:
            self.tasks.put(task)
        self.state = state
        self.count_rows = count_rows  # optional: body -> number of rows, shown in the log
        self.in_flight = 0
        self.saved = 0
        self.with_rows = 0
        self.no_data = 0
        self.failed = []

    def next_task(self):
        """Return a task, None to try again shortly, or False when all work is finished."""
        with lock:
            try:
                task = self.tasks.get_nowait()
            except queue.Empty:
                return None if self.in_flight else False
            self.in_flight += 1
            return task

    def finish(self):
        with lock:
            self.in_flight -= 1

    def requeue(self, task):
        self.tasks.put(task)
        self.finish()

    def fail(self, task, reason):
        with lock:
            self.failed.append(task.name)
        log(f"FAILED {task.name}: {reason}")
        self.finish()

    def retry(self, slot, task, reason):
        task.attempts += 1
        if task.attempts >= MAX_RETRIES:
            self.fail(task, reason)
        else:
            log(f"{slot.label} retry {task.attempts}/{MAX_RETRIES} {task.name}: {reason}")
            self.requeue(task)

    def mark_no_data(self, slot, task, status):
        with lock:
            self.state.no_data[task.name] = status
            self.state.save()
            self.no_data += 1
        log(f"{slot.label} no data {task.name} (HTTP {status})")
        self.finish()

    def store(self, slot, task, body):
        write_json(task.file, body)
        rows = self.count_rows(body) if self.count_rows else None
        with lock:
            self.saved += 1
            self.with_rows += 1 if rows else 0
        detail = f"{rows} rows, " if rows is not None else ""
        log(f"{slot.label} saved {task.name} ({detail}{slot.used}/{DAILY_LIMIT} today)")
        self.finish()

    def handle(self, slot, task):
        try:
            resp = slot.get(f"{API_BASE}{task.path}", task.params)
        except requests.RequestException as e:
            # The class name only: exception text can contain the proxy URL.
            slot.new_ip()
            self.retry(slot, task, type(e).__name__)
            return
        if resp is None:  # Ctrl+C while waiting
            self.requeue(task)
            return

        status = resp.status_code
        if status != 429:
            slot.consecutive_429 = 0
        if status == 200 and resp.content.strip():
            try:
                body = resp.json()
            except ValueError:
                self.retry(slot, task, "response was not JSON")
                return
            self.store(slot, task, body)
        elif status in (200, 204, 404):
            self.mark_no_data(slot, task, status)
        elif status == 429:
            slot.consecutive_429 += 1
            slot.cool_down(resp)
            if slot.consecutive_429 >= MAX_CONSECUTIVE_429:
                slot.retire("rate limited repeatedly")
            self.requeue(task)
        elif status in (401, 403):
            slot.retire(f"key rejected (HTTP {status})")
            self.requeue(task)
        elif status >= 500:
            self.retry(slot, task, f"HTTP {status}")
        else:
            self.fail(task, f"HTTP {status}: {resp.text[:200]}")

    def worker(self, slot):
        while not stop.is_set():
            if slot.used >= DAILY_LIMIT:
                slot.retire("daily limit reached")
            if slot.retired:
                return
            task = self.next_task()
            if task is False:
                return
            if task is None:
                stop.wait(1)
                continue
            try:
                self.handle(slot, task)
            except Exception as e:  # keep the other workers and the saved data safe
                self.fail(task, type(e).__name__)


def run_tasks(tasks, slots, state, count_rows=None):
    """Fetch every task with one worker thread per key. Ctrl+C stops cleanly. Returns the Run."""
    run = Run(tasks, state, count_rows)
    threads = [threading.Thread(target=run.worker, args=(s,), daemon=True) for s in slots]
    for thread in threads:
        thread.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("Stopping. Everything fetched so far is saved.")
        stop.set()
        for thread in threads:
            thread.join(timeout=TIMEOUT + 5)
    return run
