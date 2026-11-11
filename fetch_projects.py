"""Download Argaam Projects & Capital Investments data into data/projects/.

Stages, because each list tells the script what to fetch next:
  1. projects_by_market    1 call per market (3 = TASI, 14 = NOMU): every project in it, as one big page
  2. project_details       1 call per project in those lists: description, cost and its unit, dates, companies
  3. company_developments  1 call per listed company (from data/fundamentals/market_companies/): its key developments

Skipped on purpose: /projects/by-company/{symbol} returns rows of the same market lists, and each project's
record already names its owner and related companies, so the tab builds a company's projects from the records.

After every run the script also writes data/projects/_company_projects.json: for each listed company, the
projects whose saved record names it (as owner or related company). The tab's company view reads that one file
instead of opening every project record. `--index` rebuilds it without any API calls.

Argaam's daily limit (100 per key) counts each endpoint separately, so stages 2 and 3 do not use up each other's
calls. Every response is saved as soon as it arrives, and data/projects/_progress.json records what happened to
each item, so running again continues where it stopped.

    python fetch_projects.py --dry-run            # calls left and about how many days, no API calls
    python fetch_projects.py --sample 15          # at most 15 new items per stage, a mix of statuses and markets
    python fetch_projects.py --markets 14         # only these markets
    python fetch_projects.py --symbols 2222 2010  # developments only for these companies
    python fetch_projects.py --limit 20           # at most 20 items in all (for testing)
    python fetch_projects.py                      # everything still missing
    python fetch_projects.py --refresh            # download everything again (e.g. to pick up new projects)
    python fetch_projects.py --index              # only rebuild _company_projects.json from the saved files

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math
import re
from itertools import chain, zip_longest

from argaam_client import DATA_DIR, KeyUsage, Progress, endpoint_task, now, write_json  # also loads .env
from argaam_downloader import DAILY_LIMIT, calls_left, log, make_slots, run_tasks, stop

PROJECTS_DIR = DATA_DIR / "projects"
MARKETS = [3, 14]   # TASI and NOMU, the markets the other APIs in this project use
INDEX_FILE = PROJECTS_DIR / "_company_projects.json"  # starts with "_": not an API response, like _progress.json
PAGE_SIZE = 5000    # one page holds a whole market (TASI had 3,396 rows); the default of 10 would need hundreds of calls


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


def left(tasks, progress, refresh):
    return [t for t in tasks if refresh or not (progress.is_done(t.name) or t.file.exists())]


def market_task(market_id):
    return endpoint_task("projects_by_market", marketId=market_id, page=1, pageSize=PAGE_SIZE)


def market_projects(market_tasks):
    """Every project in the saved market lists ({marketId: task}), once each (the lists repeat some rows,
    and some projects are in both markets), with the market it was first seen in."""
    projects = {}
    for market_id, task in market_tasks.items():
        if task.file.exists():
            rows = load(task)["results"]
            if len(rows) >= PAGE_SIZE:
                log(f"WARNING: {task.name} filled a whole page ({PAGE_SIZE} rows); raise PAGE_SIZE to get the rest.")
            for row in rows:
                projects.setdefault(row["projectID"], {**row, "marketId": market_id})
    return list(projects.values())


def mixed(projects):
    """The same projects reordered so the first few cover every (market, status, cost known) group in turn,
    so a --sample shows the variety instead of just the newest projects (which rarely have a cost yet)."""
    groups = {}
    for p in projects:
        groups.setdefault((p["marketId"], p["projectStatusNameEn"], p["cost"] is not None), []).append(p)
    return [p for p in chain.from_iterable(zip_longest(*groups.values())) if p is not None]


def listed_companies():
    """(symbol, companyID, market) for every company in data/fundamentals/market_companies/, TASI and NOMU
    interleaved. Symbols are saved like '1010.SE' or '9516 .SE'; the API wants just '1010'."""
    per_market = []
    for market_id in MARKETS:
        task = endpoint_task("market_companies", marketId=market_id)
        if not task.file.exists():
            log(f"{task.file.relative_to(DATA_DIR)} is not saved: fetch it in the Fundamentals tab to list its companies.")
            continue
        rows = []
        for c in load(task)["data"]["companies"]:
            symbol = re.sub(r"\s+", "", (c.get("stockSymbol") or "")).split(".")[0]
            if re.fullmatch(r"[A-Za-z0-9-]+", symbol):
                rows.append((symbol, c["companyID"], market_id))
        per_market.append(rows)
    seen, out = set(), []
    for row in chain.from_iterable(zip_longest(*per_market)):
        if row and row[0] not in seen:
            seen.add(row[0])
            out.append(row)
    return out


def companies_in_details(detail_tasks):
    """companyIDs named in the saved project records, as owner or related company."""
    ids = set()
    for task in detail_tasks:
        if task.file.exists():
            d = load(task).get("projectDetail") or {}
            for c in (d.get("projectOwnerCompanies") or []) + (d.get("projectRelatedCompanies") or []):
                ids.add(c.get("companyID"))
    return ids


def build_index(market_tasks):
    """Write INDEX_FILE: every listed company with the saved project records that name it.
    Project names, status, cost and dates come from the market lists, so the page needs nothing else."""
    rows = {p["projectID"]: p for p in market_projects(market_tasks)}
    named = {}  # companyID -> {projectID: role}
    for pid in rows:
        task = endpoint_task("project_details", projectId=pid)
        if not task.file.exists():
            continue
        d = load(task).get("projectDetail") or {}
        for role, key in (("owner", "projectOwnerCompanies"), ("related", "projectRelatedCompanies")):
            for c in d.get(key) or []:
                named.setdefault(c.get("companyID"), {}).setdefault(pid, role)  # owner wins when both
    names = {}
    for market_id in MARKETS:
        task = endpoint_task("market_companies", marketId=market_id)
        if task.file.exists():
            names.update({c["companyID"]: c["companyNameEn"].strip() for c in load(task)["data"]["companies"]})
    companies = []
    for symbol, company_id, market_id in listed_companies():
        projects = [{"projectID": pid, "role": role, "name": rows[pid]["projectNameEn"] or rows[pid]["projectNameAr"],
                     "status": rows[pid]["projectStatusNameEn"], "announced": (rows[pid]["announcedDate"] or "")[:10],
                     "country": rows[pid]["countryNameEn"], "costSarMillions": rows[pid]["cost"]}
                    for pid, role in sorted(named.get(company_id, {}).items(), key=lambda kv: -kv[0])]
        companies.append({"symbol": symbol, "companyID": company_id, "marketId": market_id,
                          "nameEn": names.get(company_id, symbol), "projects": projects})
    companies.sort(key=lambda c: c["nameEn"].lower())
    write_json(INDEX_FILE, {"built_at": now(), "companies": companies})
    with_projects = sum(bool(c["projects"]) for c in companies)
    log(f"Wrote {INDEX_FILE.relative_to(DATA_DIR)}: {len(companies)} companies, {with_projects} named in saved project records.")


def count_rows(body):
    if "results" in body:
        return len(body["results"] or [])                          # projects_by_market
    data = body.get("data") or {}
    if "developments" in data:
        return len(data["developments"] or [])                     # company_developments
    return None                                                    # project_details: one record


def run_stage(label, tasks, slots, progress, budget, has_rows=True):
    """Fetch up to budget tasks (None = all). Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    log(f"{label}: fetching {len(batch)}.")
    run = run_tasks(batch, slots, progress, count_rows=count_rows)
    rows = f" ({run.with_rows} with rows)" if has_rows else ""
    log(f"{label} done: {run.saved} saved{rows}, {run.no_data} without data, {len(run.failed)} failed.")
    return None if budget is None else budget - len(batch)


def main():
    parser = argparse.ArgumentParser(description="Download Argaam Projects & Capital Investments data into data/projects/.")
    parser.add_argument("--markets", type=int, nargs="+", help=f"only these market IDs (default: {MARKETS})")
    parser.add_argument("--symbols", nargs="+", help="key developments only for these stock symbols (default: all listed)")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--sample", type=int, help="fetch at most this many new items per stage, a mix of projects")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    parser.add_argument("--index", action="store_true", help=f"only rebuild {INDEX_FILE.name} from the saved files")
    args = parser.parse_args()

    progress = Progress(PROJECTS_DIR)
    slots = make_slots(KeyUsage())
    budget = args.limit
    per_stage = args.sample

    def cap(tasks):
        return tasks if per_stage is None else tasks[:per_stage]

    markets = args.markets or MARKETS
    market_tasks = {m: market_task(m) for m in markets}
    if args.index:
        build_index({m: market_task(m) for m in MARKETS})
        return

    def detail_tasks(refresh=args.refresh):
        projects = market_projects(market_tasks)
        if per_stage is not None:
            projects = mixed(projects)
        tasks = [endpoint_task("project_details", projectId=p["projectID"]) for p in projects]
        return tasks, left(tasks, progress, refresh)

    def development_tasks(refresh=args.refresh):
        companies = listed_companies()
        if args.symbols:
            unknown = set(args.symbols) - {s for s, _, _ in companies}
            if unknown:
                log(f"Not in the saved company lists, fetched anyway: {sorted(unknown)}")
            companies = [c for c in companies if c[0] in args.symbols] + [(s, None, None) for s in sorted(unknown)]
        # Companies named in the saved project records first, so the tab can show both views for them.
        named = companies_in_details(detail_tasks(False)[0])
        companies.sort(key=lambda c: c[1] not in named)
        tasks = [endpoint_task("company_developments", symbol=s) for s, _, _ in companies]
        return tasks, left(tasks, progress, refresh)

    markets_left = left(market_tasks.values(), progress, args.refresh)
    details, details_left = detail_tasks()
    developments, developments_left = development_tasks()
    per_day = len(slots) * DAILY_LIMIT

    log(f"Stage 1: {len(markets_left)} of {len(market_tasks)} market lists left to fetch (markets {markets}).")
    unseen = "" if not markets_left else ", plus the projects of the markets not saved yet (TASI had 1,696, NOMU 310)"
    log(f"Stage 2: {len(details)} known projects, {len(details_left)} project records left to fetch{unseen}.")
    log(f"Stage 3: {len(developments)} companies, {len(developments_left)} development lists left to fetch.")
    guess = 0 if not markets_left else 1966
    worst = max(len(markets_left), len(details_left) + guess, len(developments_left))
    days = math.ceil(worst / per_day) if worst else 0
    log(f"{len(slots)} keys with {calls_left(slots, 'projects_by_market')} market, "
        f"{calls_left(slots, 'project_details')} project and {calls_left(slots, 'company_developments')} "
        f"development calls left today, {per_day} a day for each endpoint: about {days} day(s).")
    if args.dry_run:
        return

    budget = run_stage("Stage 1 (market lists)", cap(markets_left), slots, progress, budget)
    if stop.is_set() or budget == 0:
        return build_index({m: market_task(m) for m in MARKETS})
    # The market lists saved in stage 1 tell us which projects to fetch.
    _, details_left = detail_tasks()
    budget = run_stage("Stage 2 (project records)", cap(details_left), slots, progress, budget, has_rows=False)
    build_index({m: market_task(m) for m in MARKETS})
    if stop.is_set() or budget == 0:
        return
    _, developments_left = development_tasks()
    run_stage("Stage 3 (key developments)", cap(developments_left), slots, progress, budget)

    remaining = (len(left(market_tasks.values(), progress, False)) + len(detail_tasks(False)[1])
                 + len(development_tasks(False)[1]))
    if remaining:
        log(f"{remaining} known items still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
