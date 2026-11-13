"""Download all Argaam macroeconomic data into data/macroeconomic/.

Stages, because each list tells the script what to fetch next:
  1. lists              1 call each: indicator groups, commodities, latest commodity quotes, refining margins,
                        consumer goods and their latest prices, the petrochemical index (latest and history),
                        petrochemical products, and the valuation of each market (TASI, NOMU)
  2. indicator_fields   1 call per indicator group: the fields (indicators) inside it
  3. commodity history  1 call per commodity, by its type: Regular -> commodity_history,
                        Others -> commodity_other_history, Shipping -> commodity_shipping
  4. consumer_history   1 call per consumer good: every recorded price
  5. petro_history      1 call per petrochemical product (in its region): every recorded price
  6. indicator_values   1 call per field PER YEAR: Argaam returns one calendar year per call (without a year,
                        only the latest). Years are fetched newest first, from this year back to --from-year.
                        With --gap N a field stops after N empty years in a row, counted from its newest year with data.

Histories (stages 3-5, refining margins, the index history) ask for everything since FROM_DATE in one call.
Argaam's daily limit (100 per key) counts each endpoint separately, so the stages do not use up each other's calls.
Every response is saved as soon as it arrives, and data/macroeconomic/_progress.json records what happened
to each item, so running again continues where it stopped.

    python fetch_macroeconomic.py --dry-run          # calls left and about how many days, no API calls
    python fetch_macroeconomic.py --sample 15        # at most 15 new items per stage (indicators: 15 fields, every year)
    python fetch_macroeconomic.py --limit 20         # a small test: at most 20 calls in all
    python fetch_macroeconomic.py                    # everything still missing
    python fetch_macroeconomic.py --gap 10           # indicators: stop a field after 10 empty years in a row below its data
    python fetch_macroeconomic.py --refresh          # lists and histories again, and indicator values of this and last year

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math
from collections import defaultdict
from itertools import zip_longest

from argaam_client import MACRO_DIR, KeyUsage, Progress, endpoint_task, item_name, now, today  # also loads .env
from argaam_downloader import DAILY_LIMIT, calls_left, log, make_slots, run_tasks, stop

FROM_DATE = "1980-01-01"  # before the oldest history (petrochemical index 2006, milk powder 1998), so one call gets it all
FROM_YEAR = 1970          # oldest indicator year asked for; Saudi GDP starts by 1990, and 1970 is empty
MARKETS = (3, 14)         # TASI, NOMU, as in the other APIs
HISTORY_BY_TYPE = {"Regular": "commodity_history", "Others": "commodity_other_history", "Shipping": "commodity_shipping"}


def dates():
    return {"from": FROM_DATE, "to": today()}


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


class Plan:
    """What counts as done. Normally: saved or no_data. With --refresh: only what this run fetched,
    for the tasks refresh applies to."""

    def __init__(self, progress, refresh):
        self.progress, self.refresh, self.started = progress, refresh, now()

    def settled(self, name, refreshable=True):
        entry = self.progress.items.get(name)
        if not entry or entry["status"] not in ("saved", "no_data"):
            return False
        return not (self.refresh and refreshable) or entry.get("fetched_at", "") >= self.started

    def left(self, tasks):
        return [t for t in tasks if not self.settled(t.name)]


def spread(items, key, n):
    """Up to n items (None = all), taking turns between the values of key, so a sample shows the variety."""
    by = defaultdict(list)
    for item in items:
        by[key(item)].append(item)
    mixed = [x for group in zip_longest(*by.values()) for x in group if x is not None]
    return mixed[:n]


# ---- Stage 1: lists ------------------------------------------------------------------------------

def list_tasks():
    return [endpoint_task("indicator_groups"), endpoint_task("commodities"), endpoint_task("commodity_quotes"),
            endpoint_task("refining_margins", **dates()), endpoint_task("consumer_goods"),
            endpoint_task("consumer_prices"), endpoint_task("petro_index"),
            endpoint_task("petro_index_history", **dates()), endpoint_task("petro_products"),
            *[endpoint_task("market_indicators", marketId=m) for m in MARKETS]]


def saved_list(endpoint_id):
    task = endpoint_task(endpoint_id)
    return load(task) if task.file.exists() else None


# ---- Stage 2: indicator fields -------------------------------------------------------------------

def group_ids(groups):
    """{groupId: main group} for every group that has fields: each sub-group, or a main group without sub-groups."""
    ids = {}
    for group in groups or []:
        subs = group.get("subGroups") or []
        for sub in subs or [group]:
            ids[sub["groupID"]] = group["groupID"]
    return dict(sorted(ids.items()))


def indicator_fields(field_tasks, main_of):
    """(main group, groupId, fieldId) for every field in the saved field lists."""
    out = []
    for gid, task in field_tasks.items():
        if task.file.exists():
            body = load(task)
            out += [(main_of[gid], gid, f["fieldID"]) for f in (body if isinstance(body, list) else [])]
    return out


# ---- Stages 3-5: histories -----------------------------------------------------------------------

def commodity_tasks():
    items = saved_list("commodities") or []
    return [(c["type"], endpoint_task(HISTORY_BY_TYPE[c["type"]], commodityId=c["commodityID"], **dates()))
            for c in items if c.get("type") in HISTORY_BY_TYPE]


def consumer_tasks():
    return [(cat["categoryID"], endpoint_task("consumer_history", materialId=m["materialID"], **dates()))
            for cat in saved_list("consumer_goods") or [] for m in cat.get("consumerGoods") or []]


def petro_tasks():
    return [(p.get("categoryID"), endpoint_task("petro_history", productId=p["productID"], regionId=p["regionID"], **dates()))
            for p in saved_list("petro_products") or []]


# ---- Stage 6: indicator values, one call per field per year -------------------------------------

class Years:
    """For each field, its years newest first. A field's next year to fetch is the newest one not settled yet;
    with a gap, a field is finished after that many no_data years in a row below its newest saved year."""

    def __init__(self, fields, from_year, gap, plan):
        self.this_year = int(today()[:4])
        self.years = list(range(self.this_year, from_year - 1, -1))
        self.gap, self.plan = gap, plan
        # Names computed once: there are thousands of fields times dozens of years.
        self.names = {(g, f): [item_name("indicator_values", groupId=g, fieldId=f, year=y) for y in self.years]
                      for _, g, f in fields}

    def refreshable(self, year):
        return year >= self.this_year - 1  # only recent years get new numbers

    def next_year(self, key, skip=()):
        """The next year to fetch for this field, or None when it is finished (or blocked by a failure this run).
        The gap only counts empty years older than the field's newest saved year: an indicator that stopped being
        published years ago starts with many empty years, and those must not end it before its data is reached."""
        empty, seen_data = 0, False
        for year, name in zip(self.years, self.names[key]):
            if not self.plan.settled(name, self.refreshable(year)):
                return None if name in skip else year
            if self.plan.progress.status(name) == "no_data":
                empty += seen_data
                if self.gap and empty >= self.gap:
                    return None
            else:
                empty, seen_data = 0, True
        return None

    def left_at_most(self, key):
        """Calls this field may still need: every year not settled, ignoring the gap rule."""
        return sum(1 for year, name in zip(self.years, self.names[key]) if not self.plan.settled(name, self.refreshable(year)))


def count_rows(body):
    if isinstance(body, list):
        return len(body)                       # lists and most histories
    if isinstance(body, dict) and "values" in body:
        return len(body.get("values") or [])   # indicator_values: {"values": [...]}
    if isinstance(body, dict) and "prices" in body:
        return len(body.get("prices") or [])   # consumer_history: {"materialID": ..., "prices": [...]}
    return None                                # one object (latest index, market valuation)


def run_stage(label, tasks, slots, progress, budget):
    """Fetch up to budget tasks (None = all). Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    log(f"{label}: fetching {len(batch)}.")
    run = run_tasks(batch, slots, progress, count_rows=count_rows)
    log(f"{label} done: {run.saved} saved ({run.with_rows} with rows), {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    return None if budget is None else budget - len(batch)


def run_values(years, keys, slots, progress, budget):
    """Stage 6 in rounds: each round fetches the next year of every unfinished field."""
    tried = set()
    saved = no_data = failed = 0
    while not stop.is_set() and budget != 0:
        batch = []
        for key in keys:
            year = years.next_year(key, skip=tried)
            if year is not None:
                batch.append(endpoint_task("indicator_values", groupId=key[0], fieldId=key[1], year=year))
        batch = batch if budget is None else batch[:budget]
        if not batch:
            break
        if not calls_left(slots, "indicator_values"):
            log("Stage 6: no indicator_values calls left today. Run this script again tomorrow to continue.")
            break
        log(f"Stage 6 (indicator values): {len(batch)} fields, years {max(int(t.name[-4:]) for t in batch)} "
            f"to {min(int(t.name[-4:]) for t in batch)}.")
        run = run_tasks(batch, slots, progress, count_rows=count_rows)
        tried.update(t.name for t in batch)
        saved, no_data, failed = saved + run.saved, no_data + run.no_data, failed + len(run.failed)
        budget = None if budget is None else budget - len(batch)
    log(f"Stage 6 done: {saved} years saved, {no_data} years without data, {failed} failed.")


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam macroeconomic data into data/macroeconomic/.")
    parser.add_argument("--sample", type=int, help="at most this many new items per stage (indicators: this many fields, every year)")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--from-year", type=int, default=FROM_YEAR, help=f"oldest indicator year to ask for (default {FROM_YEAR})")
    parser.add_argument("--gap", type=int, default=0, help="stop a field after this many empty years in a row, counted below its newest year with data (default 0: ask every year)")
    parser.add_argument("--refresh", action="store_true", help="download lists, histories and the last two indicator years again")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(MACRO_DIR)
    plan = Plan(progress, args.refresh)
    slots = make_slots(KeyUsage())
    budget, n = args.limit, args.sample
    per_day = len(slots) * DAILY_LIMIT

    def stages():
        groups = saved_list("indicator_groups")
        main_of = group_ids(groups)
        fields = {gid: endpoint_task("indicator_fields", groupId=gid) for gid in main_of}
        return groups, main_of, fields

    lists_left = plan.left(list_tasks())
    groups, main_of, fields = stages()
    if args.dry_run:
        fields_left = plan.left(fields.values())
        found = indicator_fields(fields, main_of)
        years = Years(found, args.from_year, args.gap, plan)
        values_max = sum(years.left_at_most((g, f)) for _, g, f in found)
        known = len(fields) - len(fields_left)
        guess = round(len(found) / known * len(fields_left) * len(years.years)) if known else 0
        histories = {"commodities": plan.left(t for _, t in commodity_tasks()),
                     "consumer goods": plan.left(t for _, t in consumer_tasks()),
                     "petrochemical products": plan.left(t for _, t in petro_tasks())}
        log(f"Stage 1: {len(lists_left)} of {len(list_tasks())} lists left to fetch.")
        log(f"Stage 2: {len(fields_left)} of {len(fields)} indicator field lists left to fetch.")
        sources = {"commodities": "commodities", "consumer goods": "consumer_goods", "petrochemical products": "petro_products"}
        for i, (what, left) in enumerate(histories.items(), start=3):
            if saved_list(sources[what]) is None:
                log(f"Stage {i}: unknown until the {what} list is saved (stage 1).")
            else:
                log(f"Stage {i}: {len(left)} {what} histories left to fetch.")
        gap = f"fewer with --gap {args.gap}, since fields stop after empty years" if args.gap else "every year asked for"
        log(f"Stage 6: {len(found)} known fields x {len(years.years)} years ({years.this_year} to {args.from_year}): "
            f"at most {values_max} calls left ({gap}), plus up to {guess} for the fields not listed yet.")
        days = math.ceil(max(len(fields_left), *(len(v) for v in histories.values()), values_max + guess) / per_day)
        log(f"{len(slots)} keys, {per_day} calls a day for each endpoint. Today left: "
            f"{calls_left(slots, 'indicator_values')} indicator values, {calls_left(slots, 'consumer_history')} consumer "
            f"history, {calls_left(slots, 'commodity_history')} commodity history. About {days} day(s) at most.")
        return

    budget = run_stage("Stage 1 (lists)", lists_left, slots, progress, budget)
    groups, main_of, fields = stages()
    if not groups:
        raise SystemExit("Could not download the indicator groups.")

    steps = [("Stage 2 (indicator field lists)", lambda: plan.left(fields.values())[:n]),
             ("Stage 3 (commodity histories)", lambda: [t for _, t in spread([x for x in commodity_tasks() if not plan.settled(x[1].name)], lambda x: x[0], n)]),
             ("Stage 4 (consumer good histories)", lambda: [t for _, t in spread([x for x in consumer_tasks() if not plan.settled(x[1].name)], lambda x: x[0], n)]),
             ("Stage 5 (petrochemical histories)", lambda: [t for _, t in spread([x for x in petro_tasks() if not plan.settled(x[1].name)], lambda x: x[0], n)])]
    for label, tasks in steps:
        if stop.is_set() or budget == 0:
            return
        budget = run_stage(label, tasks(), slots, progress, budget)

    if stop.is_set() or budget == 0:
        return
    found = indicator_fields(fields, main_of)
    years = Years(found, args.from_year, args.gap, plan)
    keys = [(g, f) for _, g, f in found if years.next_year((g, f)) is not None]
    if n is not None:
        # A sample: fields that already have a saved year first (known to have data), then one per main group in turn.
        has_data = {k for k in keys if any(progress.status(name) == "saved" for name in years.names[k])}
        rest = spread([(m, g, f) for m, g, f in found if (g, f) in set(keys) - has_data], lambda x: x[0], None)
        keys = (sorted(has_data) + [(g, f) for _, g, f in rest])[:n]
    run_values(years, keys, slots, progress, budget)


if __name__ == "__main__":
    main()
