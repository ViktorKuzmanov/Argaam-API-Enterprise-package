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

from argaam_client import FUNDAMENTALS_DIR, write_json  # also loads .env
from argaam_downloader import STATE_DIR, FetchState, Task, calls_left, fetch_one, log, make_slots, run_tasks

STATE_FILE = STATE_DIR / "analyst_estimates.json"


def estimate_task(market, symbol, period):
    name = f"analyst_estimates_{market}_{symbol}_{period}"
    return Task(
        name=name,
        path=f"/companies/{symbol}/analyst-estimates",
        file=FUNDAMENTALS_DIR / f"{name}.json",
        params={"marketId": market, "period": period},
    )


def count_estimates(body):
    return len((body.get("data") or {}).get("estimates") or [])


def company_symbols(market, slots, refresh):
    """Return the market's symbols, using the saved company list when there is one."""
    file = FUNDAMENTALS_DIR / f"companies_market_{market}.json"
    if file.exists() and not refresh:
        body = json.loads(file.read_text(encoding="utf-8"))
    else:
        body = fetch_one(slots, f"/markets/{market}/companies", what=f"the company list for market {market}")
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


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam analyst estimates into data/fundamentals/.")
    parser.add_argument("--markets", type=int, nargs="+", default=[3, 14], help="3 = TASI, 14 = NOMU")
    parser.add_argument("--periods", nargs="+", default=["year", "quarter"], choices=["year", "quarter"])
    parser.add_argument("--limit", type=int, help="fetch at most this many (for testing)")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    state = FetchState(STATE_FILE)
    slots = make_slots(state)
    tasks, total = [], 0
    for market in args.markets:
        for symbol in company_symbols(market, slots, args.refresh):
            for period in args.periods:
                total += 1
                task = estimate_task(market, symbol, period)
                done = task.file.exists() or task.name in state.no_data
                if args.refresh or not done:
                    tasks.append(task)

    left = len(tasks)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    log(f"{total} company/period combinations, {left} left to fetch, {len(tasks)} this run.")
    log(f"{len(slots)} keys with {calls_left(slots)} calls left today.")
    if args.dry_run or not tasks:
        return

    run = run_tasks(tasks, slots, state, count_rows=count_estimates)
    remaining = left - run.saved - run.no_data
    log(f"Done: {run.saved} saved ({run.with_rows} with estimates), {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    if remaining > 0:
        log(f"{remaining} still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
