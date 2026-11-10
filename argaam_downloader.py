"""Bulk downloader shared by every fetch_*.py script.

A fetch script only decides WHAT to fetch (a list of Task objects). This file decides
HOW: each key in ARGAAM_API_KEYS gets its own worker thread, HTTP session and Data
Impulse exit IP, requests are paced and retried, rate limits are respected, and every
response is written to disk as soon as it arrives, so a stopped run can resume.

The bookkeeping it writes (key usage and data/<api>/_progress.json) is defined in
argaam_client.py, because the web app records its own fetches in the same files.
"""
import os
import queue
import random
import threading
import time
from datetime import datetime
from urllib.parse import quote

import requests

from argaam_client import (  # also loads .env
    API_BASE,
    KeyUsage,
    Progress,
    Task,
    endpoint_task,
    fingerprint,
    lock,
    used_from_headers,
    write_json,
)

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

stop = threading.Event()


def log(message):
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


class Slot:
    """One API key with its own HTTP session, proxy IP and pacing."""

    def __init__(self, index, key, usage):
        self.label = f"key{index + 1:02d}"  # for the log only; usage is counted by fingerprint
        self.index = index
        self.key = key
        self.fp = fingerprint(key)
        self.usage = usage
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
        return self.usage.used(self.fp)

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
        self.usage.record(self.fp, used_from_headers(resp))
        day_left = resp.headers.get("X-RateLimit-Remaining-Day")
        if day_left is not None and int(day_left) <= 0:
            self.retire("daily limit reached")
        elif resp.headers.get("X-RateLimit-Remaining-Minute") == "0":
            self.cool_down(resp)

    def cool_down(self, resp):
        wait = resp.headers.get("Retry-After") or resp.headers.get("RateLimit-Reset") or "60"
        seconds = float(wait) if wait.replace(".", "", 1).isdigit() else 60
        self.next_at = max(self.next_at, time.monotonic() + seconds + 1)


def make_slots(usage):
    """One Slot per key in ARGAAM_API_KEYS. Stops the script if keys or proxy login are missing."""
    if not KEYS:
        raise SystemExit("Set ARGAAM_API_KEYS in .env (comma separated).")
    if not (PROXY_LOGIN and PROXY_PASSWORD):
        raise SystemExit("Set DATA_IMPULSE_LOGIN and DATA_IMPULSE_PASSWORD in .env.")
    return [Slot(i, key, usage) for i, key in enumerate(KEYS)]


def calls_left(slots):
    """Calls all keys together may still make today."""
    return sum(max(0, DAILY_LIMIT - s.used) for s in slots)


def fetch_one(slots, task, progress):
    """Fetch, save and record one task right away (e.g. a list that tells the script what to fetch next),
    trying each key in turn. Returns the response body."""
    url = f"{API_BASE}{task.path}"
    for slot in slots:
        if slot.used >= DAILY_LIMIT:
            continue
        try:
            resp = slot.get(url, task.params)
        except requests.RequestException as e:
            log(f"{slot.label} could not get {task.name}: {type(e).__name__}")
            slot.new_ip()
            continue
        if resp is not None and resp.status_code == 200:
            body = resp.json()
            write_json(task.file, body)
            progress.record(task, "saved")
            return body
        if resp is not None:
            log(f"{slot.label} {task.name}: HTTP {resp.status_code}")
    raise SystemExit(f"Could not download {task.name}.")


class Run:
    """Works through a queue of Tasks with one worker per key."""

    def __init__(self, tasks, progress, count_rows=None):
        self.tasks = queue.Queue()
        for task in tasks:
            self.tasks.put(task)
        self.progress = progress
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
        self.progress.record(task, "failed", reason=reason)
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
        self.progress.record(task, "no_data", http=status)
        with lock:
            self.no_data += 1
        log(f"{slot.label} no data {task.name} (HTTP {status})")
        self.finish()

    def store(self, slot, task, body):
        write_json(task.file, body)
        rows = self.count_rows(body) if self.count_rows else None
        self.progress.record(task, "saved", **({"rows": rows} if rows is not None else {}))
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


def run_tasks(tasks, slots, progress, count_rows=None):
    """Fetch every task with one worker thread per key. Ctrl+C stops cleanly. Returns the Run."""
    run = Run(tasks, progress, count_rows)
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
