"""Download all Argaam Fundamentals data into data/fundamentals/, most important first.

Stages, in order of importance, because each list tells the script what to fetch next:
  1. lists         about 300 calls: the companies of each market, every company's results per year and quarter
                   (market_results, FROM_YEAR to now), analyst opinions (every page), rankings, the lowest 20,
                   and market ratios
  2. per company   1 call each per company: latest statements and ratios (year and quarter), highlights,
                   report files, and analyst estimates (year and quarter)
  3. history       1 call per company per past period, for financials_history and then ratios_history:
                   first every year-end (newest first), then every quarter (newest first). A company's years
                   start where market_results first shows a result for it.
  4. estimates     only with --estimates: estimates_vs_actuals for every symbol/year/period/field found in the
                   saved analyst estimates, and market_estimates (consensus) for the main fields.
                   Off by default: they may repeat the saved analyst estimates plus financials_history.

Argaam's daily limit (100 per key) counts each endpoint separately. When a stage has used up an endpoint's
calls for today the script moves on to the next stage, so one run gets as much as today allows. Every response
is saved as soon as it arrives and data/fundamentals/_progress.json records what happened to each item, so
running again (tomorrow, or with more keys) continues where it stopped.

    python fetch_fundamentals.py --dry-run       # what is left per stage and about how many days, no API calls
    python fetch_fundamentals.py --sample 15     # at most 15 new companies per stage
    python fetch_fundamentals.py --limit 20      # a small test: at most 20 calls in all
    python fetch_fundamentals.py                 # everything still missing (as far as today's calls go)
    python fetch_fundamentals.py --estimates     # also the two estimate endpoints (stage 4)
    python fetch_fundamentals.py --refresh       # lists, latest values and this year's history again

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math
import re
from datetime import date

from argaam_client import FUNDAMENTALS_DIR, KeyUsage, Progress, endpoint_task, now  # also loads .env
from argaam_downloader import DAILY_LIMIT, calls_left, log, make_slots, run_tasks, stop

MARKETS = (3, 14)  # TASI, NOMU
FROM_YEAR = 2000   # oldest year asked for; market_results lists every current company for any year, with zeros
# Each period: market_results fiscalPeriod, the history endpoints' (period, fiscalPeriod), and the month it ends.
YEAR_END = ("year", "year", "1", 12)
QUARTERS = [(f"q{q}", "quarter", str(q + 1), 3 * q) for q in range(1, 5)]   # Argaam: Q1-Q4 = fiscalPeriod 2-5
RESULT_PERIODS = [("year", "year")] + [("quarter", f"q{q}") for q in range(1, 5)]
RANKING_METRICS = ["market-value", "net-income", "revenues", "return-on-equity", "return-on-assets",
                   "return-on-capital", "return-on-market-value", "book-value", "price-per-book-ratio", "capital",
                   "accumulated-losses", "top-100-market-value", "top-100-net-profit"]
LOWEST_METRICS = ["price-earnings", "price-per-book"]
OPINION_RECORDS = {3: 1000, 14: 10}  # NOMU answers HTTP 400 when asked for more than 10 per page
ESTIMATE_FIELDS = [54, 230, 232, 65, 72, 79, 40, 33, 58, 66]  # fields with 100+ saved analyst estimates
HISTORY = ("financials_history", "ratios_history")


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


def this_year():
    return date.today().year


class Plan:
    """What counts as done: saved or no_data. With --refresh, only what this run fetched, for refreshable tasks."""

    def __init__(self, progress, refresh):
        self.progress, self.refresh, self.started = progress, refresh, now()

    def settled(self, task, refreshable=True):
        entry = self.progress.items.get(task.name)
        if not entry or entry["status"] not in ("saved", "no_data"):
            return False
        return not (self.refresh and refreshable) or entry.get("fetched_at", "") >= self.started

    def left(self, tasks, refreshable=True):
        return [t for t in tasks if not self.settled(t, refreshable)]


def count_rows(body):
    """Rows in a response, for the log and _progress.json; None for single objects."""
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None
    if "results" in data:
        return len((data["results"] or {}).get("results") or [])
    if "financials" in data:
        return 1 if ((data["financials"] or {}).get("value") or {}).get("data") else 0
    if "ratios" in data:
        return len(((data["ratios"] or {}).get("value") or {}).get("financialRatioFields") or [])
    if "highlights" in data:
        return len((data["highlights"] or {}).get("fields") or [])
    if "reports" in data:
        return len((data["reports"] or {}).get("files") or [])
    if "opinions" in data:
        return len((data["opinions"] or {}).get("analystOpinions") or [])
    if "rankings" in data:
        return len(data["rankings"] or [])
    if "lowest20" in data:
        return len(data["lowest20"] or [])
    if "estimates" in data:
        est = data["estimates"]
        if isinstance(est, list):
            return len(est)                                     # analyst_estimates
        if isinstance(est, dict):
            v = est.get("value") if "value" in est else est.get("analysEstimates")
            return len(v or [])                                 # estimates_vs_actuals, market_estimates
        return 0
    return None


# ---- Stage 1: lists ------------------------------------------------------------------------------

def companies(market):
    """[(companyID, symbol)] from the saved company list of a market; [] when it is not saved yet."""
    task = endpoint_task("market_companies", marketId=market)
    if not task.file.exists():
        return []
    out = []
    for c in load(task)["data"]["companies"]:
        symbol = str(c.get("stockSymbol") or "").replace(" ", "").removesuffix(".SE")
        if re.fullmatch(r"[A-Za-z0-9]+", symbol):
            out.append((c["companyID"], symbol))
    return sorted(set(out), key=lambda x: x[1])


def result_tasks(markets):
    """market_results for every market, year (newest first) and period."""
    return [endpoint_task("market_results", marketId=m, year=y, period=p, fiscalPeriod=fp)
            for y in range(this_year(), FROM_YEAR - 1, -1) for m in markets for p, fp in RESULT_PERIODS]


def opinion_tasks(markets):
    """Page 1 of each market's opinions, then the other pages once page 1 says how many there are."""
    tasks = []
    for m in markets:
        first = endpoint_task("market_opinions", marketId=m, page=1, records=OPINION_RECORDS[m])
        tasks.append(first)
        if first.file.exists():
            pages = (load(first)["data"].get("opinions") or {}).get("totalPages") or 1
            tasks += [endpoint_task("market_opinions", marketId=m, page=p, records=OPINION_RECORDS[m])
                      for p in range(2, pages + 1)]
    return tasks


def list_tasks(markets):
    tasks = [endpoint_task("market_companies", marketId=m) for m in markets]
    tasks += [endpoint_task("rankings", marketId=m, metric=x) for m in markets for x in RANKING_METRICS]
    tasks += [endpoint_task("rankings_lowest", marketId=m, metric=x, period=p)
              for m in markets for x in LOWEST_METRICS for p in ("quarter", "year")]
    tasks += [endpoint_task("market_ratios", marketId=m, fiscalPeriodTypeId=t, excludeAramco=a)
              for m in markets for t in (1, 2, 3) for a in (0, 1)]
    return tasks + opinion_tasks(markets) + result_tasks(markets)


# ---- Stage 2: per company ------------------------------------------------------------------------

def company_tasks(market, symbol):
    return [endpoint_task("financials", marketId=market, symbol=symbol, period="year"),
            endpoint_task("ratios", marketId=market, symbol=symbol, period="year"),
            endpoint_task("highlights", marketId=market, symbol=symbol),
            endpoint_task("financials", marketId=market, symbol=symbol, period="quarter"),
            endpoint_task("ratios", marketId=market, symbol=symbol, period="quarter"),
            endpoint_task("financial_reports", marketId=market, symbol=symbol),
            endpoint_task("analyst_estimates", marketId=market, symbol=symbol, period="year"),
            endpoint_task("analyst_estimates", marketId=market, symbol=symbol, period="quarter")]


# ---- Stage 3: history ----------------------------------------------------------------------------

def first_years(markets):
    """{(market, companyID): first year with a result}, from the saved year-end market_results.
    A row with currentYearValue 0 means no result that year (every current company is listed for any year)."""
    first = {}
    for m in markets:
        for y in range(FROM_YEAR, this_year() + 1):
            task = endpoint_task("market_results", marketId=m, year=y, period="year", fiscalPeriod="year")
            if not task.file.exists():
                continue
            for r in ((load(task)["data"].get("results") or {}).get("results") or []):
                year = y if r.get("currentYearValue") else (y - 1 if r.get("lastYearValue") else None)
                key = (m, r["companyID"])
                if year is not None and year < first.get(key, 9999):
                    first[key] = year
    return first


def history_tasks(endpoint, chosen, first):
    """Every past period of every chosen company: all year-ends newest first, then all quarters newest first.
    A company without a known first year (no market_results yet) gets the last two years."""
    today = date.today()
    ended = lambda y, month: date(y, month, 28) < today.replace(day=1) or (y < today.year)
    by_period = {"year": [], "quarter": []}
    rows = []
    for m, cid, symbol in chosen:
        start = max(FROM_YEAR, first.get((m, cid), this_year() - 1))
        for y in range(this_year(), start - 1, -1):
            for name, period, fp, month in [YEAR_END] + QUARTERS:
                if ended(y, month):
                    rows.append((period, -y, endpoint_task(endpoint, marketId=m, symbol=symbol, year=y,
                                                           period=period, fiscalPeriod=fp)))
    for period, negyear, task in sorted(rows, key=lambda r: (r[0] != "year", r[1])):
        by_period[period].append(task)
    return by_period["year"] + by_period["quarter"]


# ---- Stage 4: estimates (only with --estimates) --------------------------------------------------

def estimate_tasks(markets):
    combos = set()
    for f in (FUNDAMENTALS_DIR / "analyst_estimates").glob("*.json"):
        symbol = f.stem.split("_")[1]
        for e in (json.loads(f.read_text(encoding="utf-8"))["data"].get("estimates") or []):
            period = "year" if e["fiscalPeriodValue"] == "YEAR" else "quarter"
            if e["forYear"] <= this_year():  # actual values exist only for past years
                combos.add((symbol, e["forYear"], period, e["fsFieldID"]))
    vs = [endpoint_task("estimates_vs_actuals", symbol=s, fiscalYear=y, period=p, fsFieldId=f)
          for s, y, p, f in sorted(combos, key=lambda c: (-c[1], c[0], c[2], c[3]))]
    consensus = [endpoint_task("market_estimates", marketId=m, year=y, period=p, fiscalPeriod=fp, fsFieldId=f)
                 for y in range(this_year() + 4, 2013, -1) for m in markets for f in ESTIMATE_FIELDS
                 for p, fp in RESULT_PERIODS]
    return vs, consensus


# ---- Running -------------------------------------------------------------------------------------

def run_stage(label, tasks, slots, progress, budget):
    """Fetch up to budget tasks (None = all), grouped by endpoint so one used-up endpoint does not stop the
    others. Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    endpoints = list(dict.fromkeys(t.endpoint for t in batch))
    for endpoint in endpoints:
        if stop.is_set():
            break
        part = [t for t in batch if t.endpoint == endpoint]
        if not calls_left(slots, endpoint):
            log(f"{label}: no {endpoint} calls left today, {len(part)} wait for the next run.")
            continue
        log(f"{label}: fetching {len(part)} {endpoint} ({calls_left(slots, endpoint)} calls left today).")
        run = run_tasks(part, slots, progress, count_rows=count_rows)
        log(f"{label} {endpoint} done: {run.saved} saved ({run.with_rows} with rows), {run.no_data} without data, "
            f"{len(run.failed)} failed, {len(part) - run.saved - run.no_data - len(run.failed)} not reached.")
    return None if budget is None else max(0, budget - len(batch))


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam Fundamentals data into data/fundamentals/.")
    parser.add_argument("--markets", type=int, nargs="+", default=list(MARKETS), help="3 = TASI, 14 = NOMU")
    parser.add_argument("--sample", type=int, help="at most this many new companies per stage")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--estimates", action="store_true", help="also fetch estimates_vs_actuals and market_estimates")
    parser.add_argument("--refresh", action="store_true", help="lists, latest values and this year's history again")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(FUNDAMENTALS_DIR)
    plan = Plan(progress, args.refresh)
    slots = make_slots(KeyUsage())
    budget, n = args.limit, args.sample
    per_day = len(slots) * DAILY_LIMIT

    def chosen():
        """(market, companyID, symbol) for every company, or a sample that takes turns between the markets."""
        per_market = [[(m, cid, s) for cid, s in companies(m)] for m in args.markets]
        mixed = [x for group in zip(*per_market) for x in group] + \
                [x for group in per_market for x in group[min(map(len, per_market)):]]
        return mixed

    def company_left():
        out = []
        for m, cid, s in chosen():
            todo = plan.left(company_tasks(m, s))
            if todo:
                out.append(todo)
        return out[:n] if n is not None else out

    def history_left(endpoint):
        first = first_years(args.markets)
        tasks = history_tasks(endpoint, chosen(), first)
        this = this_year()
        todo = [t for t in tasks if not plan.settled(t, refreshable=f"_{this}_" in t.name)]
        if n is not None:
            keep = {s for _, _, s in chosen()[:n]}
            todo = [t for t in todo if t.name.split("/")[1].split("_")[1] in keep]
        return todo

    lists = plan.left(list_tasks(args.markets))
    if args.dry_run:
        per_company = [t for group in company_left() for t in group]
        hist = {e: history_left(e) for e in HISTORY}
        log(f"Stage 1: {len(lists)} list calls left.")
        log(f"Stage 2: {len(per_company)} per-company calls left ({len(chosen())} companies).")
        if not first_years(args.markets):
            log("Stage 3: market_results not saved yet, so each company's first year is unknown; "
                "the numbers below assume only the last two years.")
        for e, todo in hist.items():
            log(f"Stage 3: {len(todo)} {e} calls left ({sum('_1' == t.name[-2:] for t in todo)} year-ends), "
                f"{calls_left(slots, e)} left today.")
        stages = [len(lists), len(per_company), *(len(v) for v in hist.values())]
        if args.estimates:
            vs, consensus = estimate_tasks(args.markets)
            vs, consensus = plan.left(vs), plan.left(consensus)
            log(f"Stage 4: {len(vs)} estimates_vs_actuals and {len(consensus)} market_estimates calls left.")
            stages += [len(vs), len(consensus)]
        log(f"{len(slots)} keys, {per_day} calls a day for each endpoint: about "
            f"{math.ceil(max(stages) / per_day)} day(s) for the biggest endpoint.")
        return

    budget = run_stage("Stage 1 (lists)", lists, slots, progress, budget)
    # Opinion pages after page 1 are known only once page 1 is saved.
    budget = run_stage("Stage 1 (more opinion pages)", plan.left(opinion_tasks(args.markets)), slots, progress, budget)
    if stop.is_set() or budget == 0:
        return
    budget = run_stage("Stage 2 (per company)", [t for group in company_left() for t in group], slots, progress, budget)
    for endpoint in HISTORY:
        if stop.is_set() or budget == 0:
            return
        budget = run_stage(f"Stage 3 ({endpoint})", history_left(endpoint), slots, progress, budget)
    if args.estimates and not stop.is_set() and budget != 0:
        vs, consensus = estimate_tasks(args.markets)
        budget = run_stage("Stage 4 (estimates vs actuals)", plan.left(vs), slots, progress, budget)
        run_stage("Stage 4 (consensus estimates)", plan.left(consensus), slots, progress, budget)

    left = len(plan.left(list_tasks(args.markets))) + sum(len(g) for g in company_left()) + \
        sum(len(history_left(e)) for e in HISTORY)
    if left:
        log(f"{left} items still to fetch. Run this script again (tomorrow, or with more keys) to continue.")
    else:
        log("Everything is fetched.")


if __name__ == "__main__":
    main()
