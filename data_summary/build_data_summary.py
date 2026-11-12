"""Write CURRENT_AVAILABLE_DATA.html: an overview of all the data saved under data/, per API and per endpoint.

    python data_summary/build_data_summary.py

Run it again after any fetch script to update the page, then open data_summary/CURRENT_AVAILABLE_DATA.html in a browser.
Each run also saves the totals to data_summary/history.json (one snapshot per day, a day starts at 5 am so late-night
fetches count to the day before) and the page shows "+N today": how much has grown since the last snapshot of an
earlier day. To record a snapshot of another copy of data/ (for example an old commit), run
    python data_summary/build_data_summary.py --seed path/to/data --taken 2026-11-11T02:23
It reads only local files (no API calls): every data/<api>/**/*.json response, each API's _progress.json, and
static/endpoints.json for the endpoint names. A new API folder shows up on its own; add a line to API_NAMES
and RECORDS below to give it a nicer name and say what one of its records is.
"""
import argparse
import html
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the project root; this script lives in data_summary/
DATA_DIR = ROOT / "data"
OUT = Path(__file__).resolve().parent / "CURRENT_AVAILABLE_DATA.html"
HISTORY = Path(__file__).resolve().parent / "history.json"
DAY_STARTS_AT = 5  # hour; fetches before 5 am count to the previous day
ENDPOINTS = {e["id"]: e for e in json.loads((ROOT / "static" / "endpoints.json").read_text(encoding="utf-8"))}

# Folder -> (name in the viewer, fetch script).
API_NAMES = {
    "macroeconomic": ("Macroeconomic", "fetch_macroeconomic.py"),
    "fundamentals": ("Fundamentals", "fetch_fundamentals.py"),
    "funds": ("Investment funds", "fetch_funds.py"),
    "m&a": ("M&A & Transactions", "fetch_ma.py"),
    "projects": ("Projects & Capital Investments", "fetch_projects.py"),
}

# APIs whose data is fully downloaded: their fetch script's --dry-run shows 0 calls left. They get a green
# "✓ Done" badge on the page; the others show "In progress". Add a folder here once its dry-run reaches 0.
DONE = {"funds", "m&a", "projects"}

# For the APIs still downloading, "What's left" on the page comes from their fetch script's --dry-run (no API calls).
# Folder -> [(pattern in the dry-run output, what to call it on the page)]; the pattern's number is the count left,
# and a count of 0 is left out. A line about days is shown as the time estimate.
LEFT = {
    "fundamentals": [
        (r"Stage 1: (\d+) list calls left", "market lists"),
        (r"Stage 2: (\d+) per-company calls left", "per-company calls (statements, ratios, estimates, reports)"),
        (r"(\d+) financials_history calls left", "historical financial statements (one company, one period each)"),
        (r"(\d+) ratios_history calls left", "historical financial ratios (one company, one period each)"),
    ],
    "macroeconomic": [
        (r"Stage 1: (\d+) of \d+ lists left", "lists"),
        (r"Stage 2: (\d+) of \d+ indicator field lists left", "indicator lists"),
        (r"Stage 3: (\d+) commodities histories left", "commodity price histories"),
        (r"Stage 4: (\d+) consumer goods histories left", "consumer goods price histories"),
        (r"Stage 5: (\d+) petrochemical products histories left", "petrochemical product price histories"),
        (r"at most (\d+) calls left", "yearly indicator values at most (one call per indicator per year, 1970 to today)"),
    ],
}
# Things left that a dry-run can't count.
LEFT_NOTES = {
    "macroeconomic": ["Rig counts: not fetched yet, because Argaam's endpoint is broken. Retry when it is fixed."],
}
DAYS = re.compile(r"[Aa]bout (\d+) day")


def whats_left(api, script):
    """(items left as (count, label), days estimate or None), read from `python <script> --dry-run`."""
    out = subprocess.run([sys.executable, script, "--dry-run"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    text = out.stdout + out.stderr
    items = []
    for pattern, label in LEFT.get(api, []):
        m = re.search(pattern, text)
        if m and int(m.group(1)):
            items.append((int(m.group(1)), label))
    days = DAYS.search(text)
    return items, int(days.group(1)) if days else None


def length(*keys):
    """How many items are in the list at body[keys...] (0 when it is missing or null)."""
    def count(body):
        for k in keys:
            body = (body or {}).get(k) if isinstance(body, dict) else None
        return len(body or [])
    return count


one = lambda body: 1  # a detail endpoint: one file is one record

# Endpoint id -> (what one record is, how to count them in one saved response).
RECORDS = {
    "indicator_groups": ("groups", len),
    "indicator_fields": ("indicators", len),
    "indicator_values": ("values", length("values")),
    "market_companies": ("companies", length("data", "companies")),
    "analyst_estimates": ("estimates", length("data", "estimates")),
    "fund_managers": ("managers", len),
    "manager_funds": ("funds", len),
    "fund_details": ("funds", one),
    "fund_history": ("daily prices", length("values")),
    "fund_movers": ("funds", lambda b: len(b.get("gainers") or []) + len(b.get("losers") or [])),
    "market_deals": ("deals", length("data", "deals")),
    "deal_details": ("deals", one),
    "projects_by_market": ("list rows", length("results")),
    "project_details": ("projects", one),
    "company_developments": ("developments", length("data", "developments")),
}


def generic_count(body):
    """For endpoints not in RECORDS: the length of the first list of objects found, else 1."""
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict):
        for v in body.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return len(v)
        for v in body.values():
            if isinstance(v, dict):
                return generic_count(v)
    return 1


def endpoint_of(api, file, data_dir=DATA_DIR):
    """Which endpoint a saved file belongs to: the endpoint of this API whose file template has the same folder."""
    rel = file.relative_to(data_dir / api).with_suffix("").as_posix()
    folder = rel.rsplit("/", 1)[0] if "/" in rel else None
    for ep in ENDPOINTS.values():
        if ep["api"] != api:
            continue
        template_folder = ep["file"].rsplit("/", 1)[0] if "/" in ep["file"] else None
        if (folder and folder == template_folder) or (not folder and ep["file"] == rel):
            return ep["id"]
    return folder or rel


def scan(data_dir=DATA_DIR):
    apis = []
    for folder in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        api = folder.name
        endpoints = defaultdict(lambda: {"files": 0, "bytes": 0, "records": 0})
        for file in folder.rglob("*.json"):
            if file.name.startswith("_"):
                continue  # bookkeeping (_progress.json, _company_projects.json), not API responses
            ep = endpoint_of(api, file, data_dir)
            row = endpoints[ep]
            row["files"] += 1
            row["bytes"] += file.stat().st_size
            try:
                body = json.loads(file.read_text(encoding="utf-8"))
                row["records"] += RECORDS.get(ep, (None, generic_count))[1](body)
            except (ValueError, TypeError, AttributeError):
                pass
        progress = {}
        if (folder / "_progress.json").exists():
            progress = json.loads((folder / "_progress.json").read_text(encoding="utf-8")).get("items", {})
        statuses = Counter(v.get("status") for v in progress.values())
        last = max((v.get("fetched_at") or "" for v in progress.values()), default="")
        name, script = API_NAMES.get(api, (api, ""))
        rows = sorted(endpoints.items(), key=lambda kv: -kv[1]["bytes"])
        apis.append({
            "api": api, "name": name, "script": script, "endpoints": rows, "last": last[:10],
            "files": sum(r["files"] for _, r in rows), "bytes": sum(r["bytes"] for _, r in rows),
            "records": sum(r["records"] for _, r in rows),
            "saved": statuses.get("saved", 0), "no_data": statuses.get("no_data", 0), "failed": statuses.get("failed", 0),
        })
    return sorted(apis, key=lambda a: -a["bytes"])


def work_day(taken):
    return (datetime.fromisoformat(taken) - timedelta(hours=DAY_STARTS_AT)).date().isoformat()


def snapshot(apis, taken):
    """The totals worth comparing later: per API and per endpoint."""
    return {"taken": taken, "apis": {a["api"]: {
        "files": a["files"], "bytes": a["bytes"], "records": a["records"], "calls": a["saved"] + a["no_data"],
        "endpoints": {ep: dict(r) for ep, r in a["endpoints"]},
    } for a in apis}}


def load_history():
    return json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []


def save_snapshot(history, snap):
    """Keep one snapshot per day: a later run on the same day replaces the earlier one."""
    history = [h for h in history if work_day(h["taken"]) != work_day(snap["taken"])] + [snap]
    history.sort(key=lambda h: h["taken"])
    HISTORY.write_text(json.dumps(history, indent=1), encoding="utf-8")
    return history


def size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024


def num(n):
    return f"{n:,}"


def big(n):
    """1,234,567 -> 1.2M, for the headline tiles."""
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e4 else num(n)


e = html.escape


def grew(now, before, fmt=num, pct=True):
    """'+1,234 (+56%)' in green when something grew since the baseline; '' when it did not or there is no baseline."""
    if before is None or now <= before:
        return ""
    if not before:
        return f'<span class="up">+{fmt(now)} new</span>'
    p = f" ({(now - before) / before * 100:+,.0f}%)" if pct else ""
    return f'<span class="up">+{fmt(now - before)}{p}</span>'


def badge(api):
    """A green "✓ Done" for fully downloaded APIs (see DONE), a grey "In progress" for the rest."""
    return '<span class="badge done">&#10003; Done</span>' if api in DONE else '<span class="badge wip">In progress</span>'


def status_section(apis, left):
    """The "Download status" card at the top: done APIs first, then what is left for the others."""
    done = [a for a in apis if a["api"] in DONE]
    todo = [a for a in apis if a["api"] not in DONE]
    rows = [f'<div class="st-row"><span class="st-name">{e(a["name"])}</span>{badge(a["api"])}'
            f'<span class="st-left muted">All data downloaded</span></div>' for a in done]
    for a in todo:
        items, days = left.get(a["api"], ([], None))
        lines = [f"<li><b>{num(n)}</b> {e(label)}</li>" for n, label in items]
        lines += [f"<li>{e(note)}</li>" for note in LEFT_NOTES.get(a["api"], [])]
        if not lines:
            lines = [f"<li>Run <code>python {e(a['script'])} --dry-run</code> to see what is left.</li>"]
        eta = f'<span class="st-eta">About {days} day{"s" if days != 1 else ""} to go at the daily API limit</span>' if days else ""
        rows.append(f'<div class="st-row"><span class="st-name">{e(a["name"])}</span>{badge(a["api"])}{eta}'
                    f'<div class="st-left"><span class="muted">What\'s left:</span><ul>{"".join(lines)}</ul></div></div>')
    return f"""
  <section class="card status">
    <h2>Download status <span class="muted st-count">{len(done)} of {len(apis)} APIs fully downloaded</span></h2>
    {"".join(rows)}
  </section>"""


def render(apis, base=None, left=None):
    """base: an earlier snapshot to compare with (None: no "+N today" numbers)."""
    b_apis = (base or {}).get("apis", {})
    def b(api, key, ep=None):
        if base is None:
            return None
        row = b_apis.get(api, {})
        if ep is not None:
            row = row.get("endpoints", {}).get(ep, {})
        return row.get(key, 0)
    def b_total(key):
        return None if base is None else sum(v.get(key, 0) for v in b_apis.values())

    total_bytes = sum(a["bytes"] for a in apis)
    total_files = sum(a["files"] for a in apis)
    total_records = sum(a["records"] for a in apis)
    total_calls = sum(a["saved"] + a["no_data"] for a in apis)
    max_bytes = max((a["bytes"] for a in apis), default=1) or 1
    built = datetime.now().astimezone().strftime("%d %b %Y, %H:%M")

    bars = "".join(f"""
      <div class="bar-row">
        <span class="bar-name">{e(a["name"])} {badge(a["api"])}</span>
        <span class="bar-track"><span class="bar" style="width:{max(a["bytes"] / max_bytes * 100, 0.6):.1f}%"></span></span>
        <span class="bar-value">{size(a["bytes"])}<small>{a["bytes"] / total_bytes * 100:.0f}%</small>{grew(a["bytes"], b(a["api"], "bytes"), size)}</span>
      </div>""" for a in apis)

    cards = []
    for a in apis:
        rows = "".join(f"""
            <tr>
              <td><b>{e(ENDPOINTS.get(ep, {}).get("name", ep))}</b><br><code>{e(ENDPOINTS.get(ep, {}).get("path", ep))}</code></td>
              <td class="n">{num(r["files"])}{grew(r["files"], b(a["api"], "files", ep), pct=False)}</td>
              <td class="n">{num(r["records"])} <small>{e(RECORDS.get(ep, ("records",))[0])}</small>{grew(r["records"], b(a["api"], "records", ep), pct=False)}</td>
              <td class="n">{size(r["bytes"])}{grew(r["bytes"], b(a["api"], "bytes", ep), size, pct=False)}</td>
            </tr>""" for ep, r in a["endpoints"])
        status = f'{num(a["saved"])} saved · {num(a["no_data"])} no data' + (f' · <span class="bad">{num(a["failed"])} failed</span>' if a["failed"] else "")
        cards.append(f"""
      <section class="card">
        <header>
          <div>
            <h2>{e(a["name"])} {badge(a["api"])}</h2>
            <p class="muted"><code>data/{e(a["api"])}/</code>{f' · <code>{e(a["script"])}</code>' if a["script"] else ""}{f' · last fetched {a["last"]}' if a["last"] else ""}</p>
          </div>
          <div class="size">{size(a["bytes"])}{grew(a["bytes"], b(a["api"], "bytes"), size)}</div>
        </header>
        <div class="kpis">
          <div><span class="k">JSON files</span><span class="v">{num(a["files"])}</span>{grew(a["files"], b(a["api"], "files"))}</div>
          <div><span class="k">Records</span><span class="v">{num(a["records"])}</span>{grew(a["records"], b(a["api"], "records"))}</div>
          <div><span class="k">Endpoints</span><span class="v">{len(a["endpoints"])}</span></div>
          <div><span class="k">API calls recorded</span><span class="v">{num(a["saved"] + a["no_data"])}</span>{grew(a["saved"] + a["no_data"], b(a["api"], "calls"))}<span class="s">{status}</span></div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Endpoint</th><th class="n">Files</th><th class="n">Records</th><th class="n">Size</th></tr></thead>
          <tbody>{rows}</tbody>
        </table></div>
      </section>""")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Current Available Data</title>
<style>
  :root {{ --bg:#f6f6f4; --card:#fff; --fg:#1a1a19; --muted:#6b6b66; --line:#e3e2dc; --accent:#2a78d6; --track:#ecebe6; --bad:#b3261e; --up:#1e7a3c; --wip:#a15c00; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#141413; --card:#1f1f1d; --fg:#f0efec; --muted:#a8a79f; --line:#34332f; --accent:#3987e5; --track:#2b2a27; --bad:#f2958d; --up:#5fd08a; --wip:#f0b45a; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, -apple-system, sans-serif; }}
  main {{ max-width:1040px; margin:0 auto; padding:40px 16px 64px; }}
  h1 {{ font-size:30px; margin:0 0 4px; letter-spacing:-0.01em; }}
  h2 {{ font-size:19px; margin:0; }}
  .muted, small, .s {{ color:var(--muted); }}
  code {{ font-size:12.5px; }}
  td code {{ word-break:break-all; color:var(--muted); }}
  .hero {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin:28px 0; }}
  .hero div {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }}
  .hero .v {{ display:block; font-size:40px; font-weight:700; line-height:1.1; font-variant-numeric:tabular-nums; letter-spacing:-0.02em; }}
  .hero .k {{ display:block; font-size:13px; color:var(--muted); margin-top:4px; }}
  .hero .main {{ border-color:var(--accent); }}
  .hero .main .v {{ color:var(--accent); }}
  .badge {{ display:inline-block; vertical-align:middle; font-size:12px; font-weight:600; padding:1px 8px; border-radius:999px; margin-left:6px; white-space:nowrap; }}
  .badge.done {{ color:var(--up); background:color-mix(in srgb, var(--up) 14%, transparent); border:1px solid color-mix(in srgb, var(--up) 40%, transparent); }}
  .badge.wip {{ color:var(--wip); background:color-mix(in srgb, var(--wip) 14%, transparent); border:1px solid color-mix(in srgb, var(--wip) 40%, transparent); }}
  .status h2 {{ margin-bottom:8px; }}
  .st-count {{ font-size:14px; font-weight:400; margin-left:8px; }}
  .st-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; padding:12px 0; border-top:1px solid var(--line); }}
  .st-name {{ font-weight:650; font-size:16px; }}
  .st-row .badge {{ font-size:13px; padding:2px 10px; margin-left:0; }}
  .st-eta {{ font-size:13px; color:var(--muted); margin-left:auto; }}
  .st-left {{ flex-basis:100%; font-size:14px; }}
  .st-row > .st-left.muted {{ flex-basis:auto; margin-left:auto; }}
  .st-left ul {{ margin:4px 0 0; padding-left:20px; }}
  .st-left li {{ margin:2px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px; margin-bottom:16px; }}
  .card header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:14px; }}
  .card header p {{ margin:2px 0 0; font-size:13px; }}
  .size {{ font-size:28px; font-weight:700; white-space:nowrap; font-variant-numeric:tabular-nums; color:var(--accent); }}
  .bars {{ display:grid; gap:10px; }}
  .bar-row {{ display:grid; grid-template-columns:minmax(120px, 230px) 1fr 120px; align-items:center; gap:12px; font-size:14px; }}
  .bar-track {{ background:var(--track); border-radius:4px; height:14px; overflow:hidden; }}
  .bar {{ display:block; height:100%; background:var(--accent); border-radius:0 4px 4px 0; }}
  .bar-value {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
  .bar-value small {{ font-weight:400; margin-left:6px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:14px; }}
  .kpis div {{ border:1px solid var(--line); border-radius:8px; padding:8px 12px; }}
  .kpis .k {{ display:block; font-size:12px; color:var(--muted); }}
  .kpis .v {{ display:block; font-size:20px; font-weight:650; font-variant-numeric:tabular-nums; }}
  .kpis .s {{ display:block; font-size:12px; }}
  .bad {{ color:var(--bad); }}
  .up {{ display:block; color:var(--up); font-size:12.5px; font-weight:600; font-variant-numeric:tabular-nums; }}
  .size .up {{ text-align:right; font-size:13px; }}
  .bar-value .up {{ font-size:12px; }}
  .since {{ font-size:13px; color:var(--muted); margin:4px 0 0; }}
  .since .up {{ display:inline; }}
  .table-wrap {{ overflow-x:auto; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:12px; color:var(--muted); font-weight:600; }}
  .n {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  footer {{ font-size:13px; color:var(--muted); margin-top:24px; }}
  @media (max-width:640px) {{ .bar-row {{ grid-template-columns:1fr 100px; }} .bar-track {{ grid-column:1 / -1; grid-row:2; }} .card header {{ flex-direction:column; }} }}
</style>
</head>
<body>
<main>
  <p><a href="../" style="color:var(--accent); text-decoration:none; font-size:14px">&larr; Back to API Data Viewer</a></p>
  <h1>Current Available Data</h1>
  <p class="muted">Everything downloaded from the Argaam APIs and saved in <code>data/</code>, ready to use. Built {built}.</p>
  {f'<p class="since"><span class="up">+green</span> = added today, compared with the previous snapshot ({datetime.fromisoformat(base["taken"]).strftime("%d %b %Y, %H:%M")}).</p>' if base else ""}

  {status_section(apis, left or {})}

  <div class="hero">
    <div class="main"><span class="v">{size(total_bytes)}</span><span class="k">of JSON data</span>{grew(total_bytes, b_total("bytes"), size)}</div>
    <div><span class="v">{big(total_records)}</span><span class="k">records ({num(total_records)})</span>{grew(total_records, b_total("records"))}</div>
    <div><span class="v">{num(total_files)}</span><span class="k">JSON files</span>{grew(total_files, b_total("files"))}</div>
    <div><span class="v">{len(apis)}</span><span class="k">APIs · {num(total_calls)} API calls recorded</span>{grew(total_calls, b_total("calls"))}</div>
  </div>

  <section class="card">
    <h2 style="margin-bottom:14px">Size by API</h2>
    <div class="bars">{bars}</div>
  </section>
  {"".join(cards)}

  <footer>
    Records = items in each saved response: one per fund price, estimate, deal, project, development and so on, so they are counted in each endpoint's own unit.
    Size is the size of the JSON files themselves; on disk it can look a little bigger.
    <b>API calls recorded</b> come from each API's <code>_progress.json</code>: "no data" means Argaam answered with nothing, which is not retried.
    Green <b>+N</b> numbers show growth since the last snapshot from an earlier day, kept in <code>data_summary/history.json</code> (a day starts at 5 am).
    To update this page after fetching more data, run <code>python data_summary/build_data_summary.py</code>.
  </footer>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=Path, help="only record a snapshot of this data folder in history.json")
    parser.add_argument("--taken", help="when that --seed data was current, e.g. 2026-11-11T02:23")
    args = parser.parse_args()
    if args.seed:
        snap = snapshot(scan(args.seed.resolve()), args.taken or datetime.now().isoformat(timespec="minutes"))
        save_snapshot(load_history(), snap)
        print(f"Recorded a snapshot of {args.seed} taken {snap['taken']} in data_summary/{HISTORY.name}.")
        return

    apis = scan()
    now = datetime.now().isoformat(timespec="minutes")
    history = save_snapshot(load_history(), snapshot(apis, now))
    earlier = [h for h in history if work_day(h["taken"]) < work_day(now)]
    left = {a["api"]: whats_left(a["api"], a["script"]) for a in apis if a["api"] not in DONE}
    OUT.write_text(render(apis, earlier[-1] if earlier else None, left), encoding="utf-8")
    total = sum(a["bytes"] for a in apis)
    print(f"Wrote data_summary/{OUT.name}: {len(apis)} APIs, {sum(a['files'] for a in apis):,} files, {size(total)}.")
    for a in apis:
        print(f"  {a['name']:<32} {a['files']:>6,} files  {a['records']:>9,} records  {size(a['bytes']):>10}")


if __name__ == "__main__":
    main()
