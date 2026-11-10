"""Download all Argaam macroeconomic data into data/macroeconomic/.

Three stages, because each list tells the script what to fetch next:
  1. indicator_groups   1 call: every main group and its sub-groups
  2. indicator_fields   1 call per sub-group: the fields (indicators) inside it
  3. indicator_values   1 call per field: its values over time

Each key in ARGAAM_API_KEYS gets its own worker and its own Data Impulse exit IP.
Every response is saved as soon as it arrives, and data/macroeconomic/_progress.json
records what happened to each item, so running again continues where it stopped.

    python fetch_macroeconomic.py --dry-run     # calls left and about how many days, no API calls
    python fetch_macroeconomic.py --limit 20    # a small test
    python fetch_macroeconomic.py               # everything still missing
    python fetch_macroeconomic.py --refresh     # download everything again

This file only decides WHAT to fetch. HOW (keys, proxy, pacing, retries, saving)
is shared with every other fetch script and lives in argaam_downloader.py.
"""
import argparse
import json
import math

from argaam_client import MACRO_DIR  # also loads .env
from argaam_downloader import (
    DAILY_LIMIT,
    KeyUsage,
    Progress,
    calls_left,
    endpoint_task,
    fetch_one,
    log,
    make_slots,
    run_tasks,
    stop,
)


def load(task):
    return json.loads(task.file.read_text(encoding="utf-8"))


def group_ids(groups):
    """The groups that have fields: every sub-group, plus any main group without sub-groups."""
    ids = set()
    for group in groups:
        subs = group.get("subGroups") or []
        if subs:
            ids.update(sub["groupID"] for sub in subs)
        else:
            ids.add(group["groupID"])
    return sorted(ids)


def field_tasks(groups):
    return {gid: endpoint_task("indicator_fields", groupId=gid) for gid in group_ids(groups)}


def value_tasks(fields):
    """One task per field, for every group whose field list is saved."""
    tasks = []
    for gid, task in fields.items():
        if not task.file.exists():
            continue
        body = load(task)
        for field in body if isinstance(body, list) else []:
            tasks.append(endpoint_task("indicator_values", groupId=gid, fieldId=field["fieldID"]))
    return tasks


def left(tasks, progress, refresh):
    return [t for t in tasks if refresh or not (progress.is_done(t.name) or t.file.exists())]


def count_rows(body):
    if isinstance(body, list):
        return len(body)                       # indicator_fields: a list of fields
    return len(body.get("values") or [])       # indicator_values: {"values": [...]}


def run_stage(label, tasks, slots, progress, budget):
    """Fetch up to budget tasks (None = all). Returns how much budget is left."""
    batch = tasks if budget is None else tasks[:budget]
    if not batch:
        return budget
    log(f"{label}: fetching {len(batch)}.")
    run = run_tasks(batch, slots, progress, count_rows=count_rows)
    log(f"{label} done: {run.saved} saved ({run.with_rows} with data), {run.no_data} without data, "
        f"{len(run.failed)} failed.")
    return None if budget is None else budget - len(batch)


def main():
    parser = argparse.ArgumentParser(description="Download all Argaam macroeconomic data into data/macroeconomic/.")
    parser.add_argument("--limit", type=int, help="fetch at most this many items in all (for testing)")
    parser.add_argument("--refresh", action="store_true", help="download again even if already saved")
    parser.add_argument("--dry-run", action="store_true", help="only report what is left to fetch")
    args = parser.parse_args()

    progress = Progress(MACRO_DIR)
    slots = make_slots(KeyUsage())
    budget = args.limit

    # Stage 1: the list of groups.
    groups_task = endpoint_task("indicator_groups")
    if groups_task.file.exists() and (args.dry_run or not args.refresh):
        groups = load(groups_task)
    elif args.dry_run:
        log("Stage 1: indicator groups are not saved yet (1 call). The other stages are unknown until they are.")
        return
    else:
        groups = fetch_one(slots, groups_task, progress)
        budget = None if budget is None else budget - 1

    # Stage 2 and 3: what is left, and an estimate for the fields we cannot see yet.
    fields = field_tasks(groups)
    fields_left = left(fields.values(), progress, args.refresh)
    values = value_tasks(fields)
    values_left = left(values, progress, args.refresh)
    known_groups = sum(1 for t in fields.values() if t.file.exists())
    unknown_groups = sum(1 for t in fields_left)
    per_group = len(values) / known_groups if known_groups else 0
    guess = round(per_group * unknown_groups)
    total = len(fields_left) + len(values_left) + guess
    per_day = len(slots) * DAILY_LIMIT

    log(f"Stage 1: {len(groups)} main groups, {len(fields)} groups with fields.")
    log(f"Stage 2: {len(fields_left)} of {len(fields)} field lists left to fetch.")
    if known_groups:
        unseen = f"plus about {guess} more ({per_group:.1f} fields per group so far)"
    else:
        unseen = "plus an unknown number until some field lists are saved"
    log(f"Stage 3: {len(values_left)} of {len(values)} known fields left to fetch, {unseen} "
        f"in the {unknown_groups} groups whose field list is not saved yet.")
    log(f"{'About ' if known_groups else 'At least '}{total} calls in all. {len(slots)} keys with {calls_left(slots)} calls left today, "
        f"{per_day} a day: about {math.ceil(total / per_day) if total else 0} day(s).")
    if args.dry_run:
        return

    budget = run_stage("Stage 2 (field lists)", fields_left, slots, progress, budget)
    if stop.is_set() or budget == 0:
        return
    # The field lists saved in stage 2 tell us which values to fetch.
    values_left = left(value_tasks(fields), progress, args.refresh)
    run_stage("Stage 3 (values)", values_left, slots, progress, budget)

    remaining = len(left(fields.values(), progress, False)) + len(left(value_tasks(fields), progress, False))
    if remaining:
        log(f"{remaining} known items still to fetch. Run this script again to continue.")


if __name__ == "__main__":
    main()
