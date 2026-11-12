"""Minimal web viewer for Argaam API data.

Run:  python app.py   ->   http://127.0.0.1:5001
"""
import json
import os
import re

import requests
from flask import Flask, jsonify, request, send_from_directory

from argaam_client import API_BASE, DATA_DIR, ENDPOINTS, fetch_and_save, known_no_data, saved_file, saved_name, today

app = Flask(__name__, static_folder="static")
# Endpoints live in static/endpoints.json (loaded by argaam_client); the published page reads that file too.


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/data_summary/CURRENT_AVAILABLE_DATA.html")
def data_summary():
    """The "View data summary" button: the page data_summary/build_data_summary.py writes."""
    return send_from_directory("data_summary", "CURRENT_AVAILABLE_DATA.html", max_age=0)


@app.get("/api/config")
def config():
    return jsonify({"base": API_BASE, "endpoints": list(ENDPOINTS.values())})


def upstream_error(e):
    """Turn an API error response into a short message the page can show."""
    resp = e.response
    if resp.status_code == 429:
        wait = resp.headers.get("Retry-After", "60")
        return jsonify({"error": f"Rate limit reached (sandbox allows 5 requests a minute, 100 a day). Try again in {wait} seconds."}), 429
    try:
        message = resp.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = resp.text[:300]
    return jsonify({"error": f"{resp.status_code}: {message}"}), 502


def no_data_answer(entry, what):
    """Argaam already had no data for this (recorded in _progress.json), so do not spend a call asking again."""
    when = f" on {entry['fetched_at'][:10]}" if entry.get("fetched_at") else ""
    return jsonify({"error": f"{what} (Argaam had no data when this was checked{when}). "
                             "Click Re-fetch from API to ask again."}), 404


@app.get("/api/fundamentals/saved")
def fundamentals_saved():
    """Every saved fundamentals file, relative to data/, like saved_files.json on the published page. The tab uses it
    to combine a company's saved history (one file per period) without calling Argaam."""
    folder = DATA_DIR / "fundamentals"
    return jsonify(sorted(p.relative_to(DATA_DIR).as_posix() for p in folder.rglob("*.json") if not p.name.startswith("_")))


@app.get("/api/fundamentals/<endpoint_id>")
def fundamentals(endpoint_id):
    """Fundamentals tab: any fundamentals endpoint in static/endpoints.json, with the values its path, query and file
    need (marketId, symbol, period, year, metric, ...). Reuses the saved copy unless refresh=1."""
    ep = ENDPOINTS.get(endpoint_id)
    if not ep or ep["api"] != "fundamentals":
        return jsonify({"error": f"{endpoint_id} is not a fundamentals endpoint in static/endpoints.json."}), 404
    names = dict.fromkeys(re.findall(r"\{(\w+)\}", ep["path"] + ep["file"]) + ep.get("query", []))
    values = {}
    for name in names:
        value = request.args.get(name, "").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]+", value):
            return jsonify({"error": f"Choose a {name}."}), 400
        values[name] = value
    file = saved_file(endpoint_id, **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this")
    try:
        data, file = fetch_and_save(endpoint_id, **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": "Argaam has no data for this."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


FUNDS_FROM = "1980-01-01"  # same as fetch_funds.py: before the oldest fund, so the history is complete


@app.get("/api/funds/<endpoint_id>")
def funds(endpoint_id):
    """Funds tab: any funds endpoint in static/endpoints.json, with managerId / fundId as needed.
    Reuses the saved copy unless refresh=1. Lists (managers, a manager's funds) feed the dropdowns."""
    ep = ENDPOINTS.get(endpoint_id)
    if not ep or ep["api"] != "funds":
        return jsonify({"error": f"{endpoint_id} is not a funds endpoint in static/endpoints.json."}), 404
    values = {}
    for name in ("managerId", "fundId"):
        if "{" + name + "}" in ep["path"]:
            value = request.args.get(name, "")
            if not value.isdigit():
                return jsonify({"error": f"Choose a {'fund manager' if name == 'managerId' else 'fund'}."}), 400
            values[name] = value
    if "from" in ep.get("query", []):
        values.update({"from": FUNDS_FROM, "to": today()})
    file = saved_file(endpoint_id, **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this fund")
    try:
        data, file = fetch_and_save(endpoint_id, **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": "Argaam has no data for this fund."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


@app.get("/api/m&a/<endpoint_id>")
def mergers(endpoint_id):
    """M&A tab: market_deals (marketId) or deal_details (dealId) from static/endpoints.json.
    Reuses the saved copy unless refresh=1."""
    ep = ENDPOINTS.get(endpoint_id)
    if not ep or ep["api"] != "m&a":
        return jsonify({"error": f"{endpoint_id} is not an M&A endpoint in static/endpoints.json."}), 404
    values = {}
    for name in ("marketId", "dealId"):
        if "{" + name + "}" in ep["path"]:
            value = request.args.get(name, "")
            if not value.isdigit():
                return jsonify({"error": f"Choose a {'market' if name == 'marketId' else 'deal'}."}), 400
            values[name] = value
    file = saved_file(endpoint_id, **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this")
    try:
        data, file = fetch_and_save(endpoint_id, **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": "Argaam has no data for this."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


PROJECTS_PAGE = {"page": 1, "pageSize": 5000}  # same as fetch_projects.py: a whole market in one page


@app.get("/api/projects-index")
def projects_index():
    """data/projects/_company_projects.json, written by fetch_projects.py: each listed company and the saved
    project records that name it. Not an API response, so it has no endpoint and no re-fetch."""
    return send_from_directory("data/projects", "_company_projects.json", max_age=0)


@app.get("/api/projects/<endpoint_id>")
def projects(endpoint_id):
    """Projects tab: projects_by_market (marketId), project_details (projectId) or company_developments (symbol)
    from static/endpoints.json. Reuses the saved copy unless refresh=1."""
    ep = ENDPOINTS.get(endpoint_id)
    if not ep or ep["api"] != "projects":
        return jsonify({"error": f"{endpoint_id} is not a projects endpoint in static/endpoints.json."}), 404
    values = {}
    for name, what, pattern in (("marketId", "market", r"\d+"), ("projectId", "project", r"\d+"),
                                ("symbol", "company", r"[A-Za-z0-9-]+")):
        if "{" + name + "}" in ep["path"]:
            value = request.args.get(name, "").strip()
            if not re.fullmatch(pattern, value):
                return jsonify({"error": f"Choose a {what}."}), 400
            values[name] = value
    if "pageSize" in ep.get("query", []):
        values.update(PROJECTS_PAGE)
    file = saved_file(endpoint_id, **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this")
    try:
        data, file = fetch_and_save(endpoint_id, **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": "Argaam has no data for this."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


MACRO_FROM = "1980-01-01"  # same as fetch_macroeconomic.py: before the oldest history, so one call gets it all
MACRO_PICKS = {"groupId": "indicator group", "fieldId": "indicator", "year": "year", "commodityId": "commodity",
               "materialId": "consumer good", "productId": "product", "regionId": "region", "marketId": "market"}


@app.get("/api/macroeconomic/saved")
def macro_saved():
    """Every saved macroeconomic file, relative to data/, like saved_files.json on the published page. The tab uses it
    to combine an indicator's saved years without calling Argaam."""
    folder = DATA_DIR / "macroeconomic"
    return jsonify(sorted(p.relative_to(DATA_DIR).as_posix() for p in folder.rglob("*.json") if not p.name.startswith("_")))


@app.get("/api/macroeconomic/<endpoint_id>")
def macroeconomic(endpoint_id):
    """Macroeconomic tab: any macroeconomic endpoint in static/endpoints.json, with its IDs (and year) as needed.
    Histories ask for everything since MACRO_FROM. Reuses the saved copy unless refresh=1."""
    ep = ENDPOINTS.get(endpoint_id)
    if not ep or ep["api"] != "macroeconomic":
        return jsonify({"error": f"{endpoint_id} is not a macroeconomic endpoint in static/endpoints.json."}), 404
    values = {}
    for name in re.findall(r"\{(\w+)\}", ep["path"]) + [q for q in ep.get("query", []) if q not in ("from", "to")]:
        value = request.args.get(name, "").strip()
        if not value.isdigit():
            return jsonify({"error": f"Choose a {MACRO_PICKS.get(name, name)}."}), 400
        values[name] = value
    if "from" in ep.get("query", []):
        values.update({"from": MACRO_FROM, "to": today()})
    file = saved_file(endpoint_id, **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this")
    try:
        data, file = fetch_and_save(endpoint_id, **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": "Argaam has no data for this."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5001)), debug=True)
