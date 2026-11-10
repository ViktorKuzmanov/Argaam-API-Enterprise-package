"""Download analyst estimates for every Argaam company into data/fundamentals/.

Each key in ARGAAM_API_KEYS gets its own worker and its own Data Impulse exit IP.
Every response is written to disk as soon as it arrives, so stopping early (rate
limit, crash, Ctrl+C) loses nothing. Run it again and it continues where it stopped.

    python fetch_all_analyst_estimates.py              # everything still missing
    python fetch_all_analyst_estimates.py --limit 5    # a small test
    python fetch_all_analyst_estimates.py --dry-run    # show what is left
    python fetch_all_analyst_estimates.py --refresh    # download everything again
"""
import argparse
import json
import os
import queue
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from argaam_client import API_BASE, FUNDAMENTALS_DIR  # also loads .env

# Kept outside data/ because everything in data/ is published to GitHub Pages.
STATE_FILE = Path(__file__).parent / ".fetch_state" / "analyst_estimates.json"

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

lock = threading.Lock()
stop = threading.Event()


def log(message):
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_json(path, data):
    """Write through a temp file so a crash can never leave half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state():
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("no_data", {})
    state.setdefault("usage", {})
    state["usage"] = {today(): state["usage"].get(today(), {})}
    return state


state = load_state()


def save_state():
    """Call while holding the lock."""
    write_json(STATE_FILE, state)


@dataclass
class Task:
    market: int
    symbol: str
    period: str
    attempts: int = 0

    @property
    def name(self):
        return f"analyst_estimates_{self.market}_{self.symbol}_{self.period}"


class Slot:
    """One API key with its own HTTP session, proxy IP and pacing."""

    def __init__(self, index, key):
        self.label = f"key{index + 1:02d}"
        self.index = index
        self.key = key
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
        return state["usage"][today()].get(self.label, 0)

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
            usage = state["usage"][today()]
            if day_left is not None and day_limit is not None:
                usage[self.label] = int(day_limit) - int(day_left)
            else:
                usage[self.label] = usage.get(self.label, 0) + 1
            save_state()
        if day_left is not None and int(day_left) <= 0:
            self.retire("daily limit reached")
        elif resp.headers.get("X-RateLimit-Remaining-Minute") == "0":
            self.cool_down(resp)

    def cool_down(self, resp):
        wait = resp.headers.get("Retry-After") or resp.headers.get("RateLimit-Reset") or "60"
        seconds = float(wait) if wait.replace(".", "", 1).isdigit() else 60
        self.next_at = max(self.next_at, time.monotonic() + seconds + 1)


class Run:
    def __init__(self, tasks):
        self.tasks = queue.Queue()
        for task in tasks:
            self.tasks.put(task)
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
            state["no_data"][task.name] = status
            save_state()
            self.no_data += 1
        log(f"{slot.label} no data {task.name} (HTTP {status})")
        self.finish()

    def store(self, slot, task, body):
        write_json(FUNDAMENTALS_DIR / f"{task.name}.json", body)
        rows = len((body.get("data") or {}).get("estimates") or [])
        with lock:
            self.saved += 1
            self.with_rows += 1 if rows else 0
        log(f"{slot.label} saved {task.name} ({rows} rows, {slot.used}/{DAILY_LIMIT} today)")
        self.finish()

    def handle(self, slot, task):
        url = f"{API_BASE}/companies/{task.symbol}/analyst-estimates"
        try:
            resp = slot.get(url, {"marketId": task.market, "period": task.period})
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


def company_symbols(market, slots, refresh):
    """Return the market's symbols, using the saved company list when there is one."""
    file = FUNDAMENTALS_DIR / f"companies_market_{market}.json"
    if file.exists() and not refresh:
        body = json.loads(file.read_text(encoding="utf-8"))
    else:
        body = download_company_list(market, slots)
        write_json(file, body)
    symbols = []
    for company in body["data"]["companies"]:
        raw = str(company.get("stockSymbol") or "")
        symbol = raw.replace(" ", "").removesuffix(".SE")
        if re.fullmatch(r"[A-Za-z0-9]+", symbol):
            symbols.append(symbol)
        else:
            log(f"Skipping company {company.get('companyID')}: unusable symbol {raw!r}")
    return sorted(set(symbols))


def download_company_list(market, slots):
    url = f"{API_BASE}/markets/{market}/companies"
    for slot in slots:
        if slot.used >= DAILY_LIMIT:
            continue
        try:
            resp = slot.get(url)
        except requests.RequestException as e:
            log(f"{slot.label} could not get market {market} list: {type(e).__name__}")
            slot.new_ip()
            continue
        if resp is not None and resp.status_code == 200:
            return resp.json()
        if resp is not None:
            log(f"{slot.label} market {market} list: HTTP {resp.status_code}")
    raise SystemExit(f"Could not download the company list for market {market}.")


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam analyst estimates into data/fundamentals/.")
    parser.add_argument("--markets", type=int, nargs="+", default=[3, 14], help="3 = TASI, 14 = NOMU")
    parser.add_argument("--periods", nargs="+", default=["year", "quarter"], choices=["year", "quarter"])
    parser.add_argument("--limit", type=int, help="fetch at most this many (for testing)")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    if not KEYS:
        raise SystemExit("Set ARGAAM_API_KEYS in .env (comma separated).")
    if not (PROXY_LOGIN and PROXY_PASSWORD):
        raise SystemExit("Set DATA_IMPULSE_LOGIN and DATA_IMPULSE_PASSWORD in .env.")

    slots = [Slot(i, key) for i, key in enumerate(KEYS)]
    tasks, total = [], 0
    for market in args.markets:
        for symbol in company_symbols(market, slots, args.refresh):
            for period in args.periods:
                total += 1
                task = Task(market, symbol, period)
                done = (FUNDAMENTALS_DIR / f"{task.name}.json").exists() or task.name in state["no_data"]
                if args.refresh or not done:
                    tasks.append(task)

    left = len(tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    available = sum(max(0, DAILY_LIMIT - s.used) for s in slots)
    log(f"{total} company/period combinations, {left} left to fetch, {len(tasks)} this run.")
    log(f"{len(slots)} keys with {available} calls left today.")
    if args.dry_run or not tasks:
        return

    run = Run(tasks)
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

    remaining = left - run.saved - run.no_data
    log(f"Done: {run.saved} saved ({run.with_rows} with estimates), {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    if remaining > 0:
        log(f"{remaining} still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
