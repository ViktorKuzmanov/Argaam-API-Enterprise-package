"""Download analyst estimates for every Argaam company into data/fundamentals/.

Each key in ARGAAM_API_KEYS gets its own worker and its own Data Impulse exit IP.
Every response is written to disk as soon as it arrives, so stopping early (rate
limit, crash, Ctrl+C) loses nothing. Run it again and it continues where it stopped.

    python fetch_all_analyst_estimates.py              # everything still missing
    python fetch_all_analyst_estimates.py --limit 5    # a small test
    python fetch_all_analyst_estimates.py --dry-run    # show what is left
    python fetch_all_analyst_estimates.py --refresh    # download everything again

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import re

from argaam_client import FUNDAMENTALS_DIR  # also loads .env
from argaam_downloader import KeyUsage, Progress, calls_left, endpoint_task, fetch_one, log, make_slots, run_tasks


def count_estimates(body):
    return len((body.get("data") or {}).get("estimates") or [])


def company_symbols(market, slots, progress, refresh):
    """Return the market's symbols, using the saved company list when there is one."""
    task = endpoint_task("market_companies", marketId=market)
    if task.file.exists() and not refresh:
        body = json.loads(task.file.read_text(encoding="utf-8"))
    else:
        body = fetch_one(slots, task, progress)
    symbols = []
    for company in body["data"]["companies"]:
        raw = str(company.get("stockSymbol") or "")
        symbol = raw.replace(" ", "").removesuffix(".SE")
        if re.fullmatch(r"[A-Za-z0-9]+", symbol):
            symbols.append(symbol)
        else:
            log(f"Skipping company {company.get('companyID')}: unusable symbol {raw!r}")
    return sorted(set(symbols))


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam analyst estimates into data/fundamentals/.")
    parser.add_argument("--markets", type=int, nargs="+", default=[3, 14], help="3 = TASI, 14 = NOMU")
    parser.add_argument("--periods", nargs="+", default=["year", "quarter"], choices=["year", "quarter"])
    parser.add_argument("--limit", type=int, help="fetch at most this many (for testing)")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(FUNDAMENTALS_DIR)
    slots = make_slots(KeyUsage())
    tasks, total = [], 0
    for market in args.markets:
        for symbol in company_symbols(market, slots, progress, args.refresh):
            for period in args.periods:
                total += 1
                task = endpoint_task("analyst_estimates", marketId=market, symbol=symbol, period=period)
                done = progress.is_done(task.name) or task.file.exists()
                if args.refresh or not done:
                    tasks.append(task)

    left = len(tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    log(f"{total} company/period combinations, {left} left to fetch, {len(tasks)} this run.")
    log(f"{len(slots)} keys with {calls_left(slots)} calls left today.")
    if args.dry_run or not tasks:
        return

    run = run_tasks(tasks, slots, progress, count_rows=count_estimates)
    remaining = left - run.saved - run.no_data
    log(f"Done: {run.saved} saved ({run.with_rows} with estimates), {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    if remaining > 0:
        log(f"{remaining} still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
