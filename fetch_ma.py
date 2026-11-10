"""Download Argaam M&A & Transactions data into data/m&a/.

Stages, because each list tells the script what to fetch next:
  1. market_deals   1 call per market (3 = TASI, 14 = NOMU): every deal in that market, no pages
  2. deal_details   1 call per deal in those lists: the full record, including how the deal was financed

Skipped on purpose: /companies/{symbol}/mergers-acquisitions returns the same records as the market
list, filtered to one company, so the tab filters the market list instead of spending a call per company.

Argaam's daily limit (100 per key) counts each endpoint separately. Every response is saved as soon as it
arrives, and data/m&a/_progress.json records what happened to each item, so running again continues where it stopped.

    python fetch_ma.py --dry-run           # calls left and about how many days, no API calls
    python fetch_ma.py --sample 15         # at most 15 new items per stage, a mix of deal types and statuses
    python fetch_ma.py --markets 14        # only these markets
    python fetch_ma.py --limit 20          # at most 20 items in all (for testing)
    python fetch_ma.py                     # everything still missing
    python fetch_ma.py --refresh           # download everything again (e.g. to pick up new deals)

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math
from itertools import chain, zip_longest

from argaam_client import DATA_DIR, KeyUsage, Progress, endpoint_task  # also loads .env
from argaam_downloader import DAILY_LIMIT, calls_left, log, make_slots, run_tasks, stop

MA_DIR = DATA_DIR / "m&a"
MARKETS = [3, 14]  # TASI and NOMU; the sandbox answers HTTP 400 for other markets (1, 4, 5 were tried)


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


def left(tasks, progress, refresh):
    return [t for t in tasks if refresh or not (progress.is_done(t.name) or t.file.exists())]


def market_deals(market_tasks):
    """Every deal in the saved market lists, in list order (newest first)."""
    deals = []
    for task in market_tasks:
        if task.file.exists():
            deals += load(task)["data"]["deals"]
    return deals


def mixed(deals):
    """The same deals reordered so the first few cover many types and statuses: one from each
    (type, status) group in turn, so a --sample shows the variety instead of just the newest deals."""
    groups = {}
    for deal in deals:
        groups.setdefault((deal["acquisitionTypeNameEn"], deal["acquisitionStatusNameEn"]), []).append(deal)
    return [d for d in chain.from_iterable(zip_longest(*groups.values())) if d is not None]


def count_rows(body):
    data = body.get("data") or {}
    return len(data["deals"]) if "deals" in data else None  # market_deals: a list; deal_details: one record


def run_stage(label, tasks, slots, progress, budget):
    """Fetch up to budget tasks (None = all). Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    log(f"{label}: fetching {len(batch)}.")
    run = run_tasks(batch, slots, progress, count_rows=count_rows)
    log(f"{label} done: {run.saved} saved, {run.no_data} without data, {len(run.failed)} failed.")
    return None if budget is None else budget - len(batch)


def main():
    parser = argparse.ArgumentParser(description="Download Argaam M&A & Transactions data into data/m&a/.")
    parser.add_argument("--markets", type=int, nargs="+", help=f"only these market IDs (default: {MARKETS})")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--sample", type=int, help="fetch at most this many new items per stage, a mix of deals")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(MA_DIR)
    slots = make_slots(KeyUsage())
    budget = args.limit
    per_stage = args.sample

    def cap(tasks):
        return tasks if per_stage is None else tasks[:per_stage]

    markets = args.markets or MARKETS
    market_tasks = [endpoint_task("market_deals", marketId=m) for m in markets]

    def detail_tasks(refresh=args.refresh):
        deals = market_deals(market_tasks)
        if per_stage is not None:
            deals = mixed(deals)
        return deals, left([endpoint_task("deal_details", dealId=d["mergerID"]) for d in deals], progress, refresh)

    markets_left = left(market_tasks, progress, args.refresh)
    deals, details_left = detail_tasks()
    per_day = len(slots) * DAILY_LIMIT

    log(f"Stage 1: {len(markets_left)} of {len(market_tasks)} market lists left to fetch (markets {markets}).")
    unseen = "" if not markets_left else ", plus the deals of the markets not saved yet (TASI had 615, NOMU 19)"
    log(f"Stage 2: {len(deals)} known deals, {len(details_left)} deal records left to fetch{unseen}.")
    days = math.ceil(max(len(markets_left), len(details_left)) / per_day) if (markets_left or details_left) else 0
    log(f"{len(slots)} keys with {calls_left(slots, 'market_deals')} market and {calls_left(slots, 'deal_details')} "
        f"deal calls left today, {per_day} a day for each endpoint: about {days} day(s).")
    if args.dry_run:
        return

    budget = run_stage("Stage 1 (market lists)", cap(markets_left), slots, progress, budget)
    if stop.is_set() or budget == 0:
        return
    # The market lists saved in stage 1 tell us which deals to fetch.
    deals, details_left = detail_tasks()
    run_stage("Stage 2 (deal records)", cap(details_left), slots, progress, budget)

    remaining = len(left(market_tasks, progress, False)) + len(detail_tasks(False)[1])
    if remaining:
        log(f"{remaining} known items still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
