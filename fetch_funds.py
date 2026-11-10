"""Download Argaam investment funds data into data/funds/.

Stages, because each list tells the script what to fetch next:
  1. fund_managers   1 call: every fund manager
  2. manager_funds   1 call per manager: the funds it runs
  3. fund_details    1 call per fund: objective, strategy, fees, minimums, size
  4. fund_history    1 call per fund: every end-of-day unit price and net asset value since FROM_DATE
plus fund_movers, 1 call: this year's 10 biggest gainers and losers.

Argaam's daily limit (100 per key) counts each endpoint separately, so stages 3 and 4 do not use up each other's calls.
Every response is saved as soon as it arrives, and data/funds/_progress.json records what happened
to each item, so running again continues where it stopped.

    python fetch_funds.py --dry-run                 # calls left and about how many days, no API calls
    python fetch_funds.py --managers 2604 2501      # only these managers (IDs from data/funds/fund_managers.json)
    python fetch_funds.py --limit 20                # a small test
    python fetch_funds.py                           # everything still missing
    python fetch_funds.py --refresh                 # download everything again (e.g. to get newer prices)

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math

from argaam_client import DATA_DIR, KeyUsage, Progress, endpoint_task, today  # also loads .env
from argaam_downloader import DAILY_LIMIT, calls_left, fetch_one, log, make_slots, run_tasks, stop

FUNDS_DIR = DATA_DIR / "funds"
FROM_DATE = "1980-01-01"  # before the oldest fund (1990), so the history call returns everything


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


def left(tasks, progress, refresh):
    return [t for t in tasks if refresh or not (progress.is_done(t.name) or t.file.exists())]


def fund_ids(list_tasks):
    """(managerId, fundId) for every fund in the managers' saved fund lists."""
    ids = []
    for manager_id, task in list_tasks.items():
        if task.file.exists():
            body = load(task)
            ids += [(manager_id, fund["fundID"]) for fund in (body if isinstance(body, list) else [])]
    return ids


def count_rows(body):
    if isinstance(body, list):
        return len(body)                       # manager_funds: a list of funds
    if "values" in body:
        return len(body.get("values") or [])   # fund_history: {"values": [...]}
    return None                                # fund_details: one object


def run_stage(label, tasks, slots, progress, budget, has_rows=True):
    """Fetch up to budget tasks (None = all). Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    log(f"{label}: fetching {len(batch)}.")
    run = run_tasks(batch, slots, progress, count_rows=count_rows)
    rows = f" ({run.with_rows} with rows)" if has_rows else ""
    log(f"{label} done: {run.saved} saved{rows}, {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    return None if budget is None else budget - len(batch)


def main():
    parser = argparse.ArgumentParser(description="Download Argaam investment funds data into data/funds/.")
    parser.add_argument("--managers", type=int, nargs="+", help="only these fund manager IDs (default: all)")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(FUNDS_DIR)
    slots = make_slots(KeyUsage())
    budget = args.limit

    # Stage 1: the list of managers, and the movers (one call each).
    managers_task = endpoint_task("fund_managers")
    if managers_task.file.exists() and (args.dry_run or not args.refresh):
        managers = load(managers_task)
    elif args.dry_run:
        log("Stage 1: fund managers are not saved yet (1 call). The other stages are unknown until they are.")
        return
    else:
        managers = fetch_one(slots, managers_task, progress)
        budget = None if budget is None else budget - 1
    movers_task = endpoint_task("fund_movers")
    if not args.dry_run and (args.refresh or not movers_task.file.exists()) and budget != 0:
        fetch_one(slots, movers_task, progress)
        budget = None if budget is None else budget - 1

    ids = [m["fundManagerID"] for m in managers]
    if args.managers:
        unknown = set(args.managers) - set(ids)
        if unknown:
            raise SystemExit(f"Not in data/funds/fund_managers.json: {sorted(unknown)}")
        ids = [i for i in ids if i in args.managers]

    # Stages 2-4: what is left, and an estimate for the managers whose fund list we cannot see yet.
    lists = {mid: endpoint_task("manager_funds", managerId=mid) for mid in ids}
    lists_left = left(lists.values(), progress, args.refresh)

    def fund_stages():
        funds = fund_ids(lists)
        details = [endpoint_task("fund_details", managerId=m, fundId=f) for m, f in funds]
        history = [endpoint_task("fund_history", managerId=m, fundId=f, **{"from": FROM_DATE, "to": today()})
                   for m, f in funds]
        return funds, left(details, progress, args.refresh), left(history, progress, args.refresh)

    funds, details_left, history_left = fund_stages()
    known = len(lists) - len(lists_left)
    per_manager = len(funds) / known if known else 0
    guess = round(per_manager * len(lists_left))
    per_day = len(slots) * DAILY_LIMIT

    log(f"Stage 1: {len(managers)} fund managers, {len(ids)} selected.")
    log(f"Stage 2: {len(lists_left)} of {len(lists)} fund lists left to fetch.")
    unseen = (f"plus about {guess} more ({per_manager:.1f} funds per manager so far)" if known
              else "plus an unknown number until some fund lists are saved")
    log(f"Stages 3 and 4: {len(funds)} known funds, {len(details_left)} details and {len(history_left)} "
        f"price histories left to fetch, {unseen}.")
    days = math.ceil(max(len(lists_left), len(details_left) + guess, len(history_left) + guess) / per_day)
    log(f"{len(slots)} keys with {calls_left(slots, 'fund_details')} details and {calls_left(slots, 'fund_history')} "
        f"history calls left today, {per_day} a day for each endpoint: about {days} day(s).")
    if args.dry_run:
        return

    budget = run_stage("Stage 2 (fund lists)", lists_left, slots, progress, budget)
    if stop.is_set() or budget == 0:
        return
    # The fund lists saved in stage 2 tell us which funds to fetch.
    funds, details_left, history_left = fund_stages()
    budget = run_stage("Stage 3 (fund details)", details_left, slots, progress, budget, has_rows=False)
    if stop.is_set() or budget == 0:
        return
    run_stage("Stage 4 (price history)", history_left, slots, progress, budget)

    remaining = sum(len(t) for t in (left(lists.values(), progress, False), *fund_stages()[1:]))
    if remaining:
        log(f"{remaining} known items still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
