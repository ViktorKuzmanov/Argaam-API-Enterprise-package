"""Minimal web viewer for Argaam API data.

Run:  python app.py   ->   http://127.0.0.1:5001
"""
import json
import os
import re

import requests
from flask import Flask, jsonify, request, send_from_directory

from argaam_client import API_BASE, ENDPOINTS, fetch_and_save, known_no_data, match_path, saved_file, saved_name, today

app = Flask(__name__, static_folder="static")
# Endpoints live in static/endpoints.json (loaded by argaam_client); the published page reads that file too.


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify({"base": API_BASE, "endpoints": list(ENDPOINTS.values())})


def cached(endpoint_id, **values):
    """Return the saved response if there is one, otherwise fetch it and save it."""
    file = saved_file(endpoint_id, **values)
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    data, _ = fetch_and_save(endpoint_id, **values)
    return data


def lookup(endpoint_id, **values):
    """Serve a cached lookup list (used by the Group / Field dropdowns)."""
    try:
        return jsonify(cached(endpoint_id, **values))
    except requests.HTTPError as e:
        return jsonify({"error": f"{e.response.status_code}: {e.response.text[:300]}"}), 502
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/groups")
def groups():
    return lookup("indicator_groups")


@app.get("/api/groups/<int:group_id>/fields")
def group_fields(group_id):
    return lookup("indicator_fields", groupId=group_id)


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


@app.get("/api/fundamentals/analyst-estimates")
def analyst_estimates():
    """Estimates for one company. Reuses the saved copy unless refresh=1, because the sandbox limit is tight."""
    symbol = request.args.get("symbol", "").strip()
    market_id = request.args.get("marketId", "")
    period = request.args.get("period", "year")
    if not re.fullmatch(r"[A-Za-z0-9]+", symbol):
        return jsonify({"error": "Enter a stock symbol, e.g. 2222."}), 400
    if not market_id.isdigit():
        return jsonify({"error": "Choose a market."}), 400
    if period not in ("year", "quarter"):
        return jsonify({"error": "Period must be year or quarter."}), 400

    values = {"marketId": market_id, "symbol": symbol, "period": period}
    file = saved_file("analyst_estimates", **values)
    refresh = request.args.get("refresh") == "1"
    if file.exists() and not refresh:
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if not refresh and (entry := known_no_data("analyst_estimates", **values)):
        return no_data_answer(entry, f"No analyst estimates for symbol {symbol} on this market")
    try:
        data, file = fetch_and_save("analyst_estimates", **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": f"No analyst estimates for symbol {symbol} on this market."}), 404
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


@app.post("/api/fetch")
def fetch_endpoint():
    """Macroeconomic tab: saves under data/macroeconomic/. Reuses the saved copy unless refresh is set.
    The path must match one of the macroeconomic endpoints in static/endpoints.json, which decides the file.
    Saved files come from API_BASE, so another base always fetches."""
    body = request.get_json(force=True)
    path = body.get("path", "")
    if "{" in path:
        return jsonify({"error": "Fill in the {placeholders} in the path first."}), 400
    matched = match_path(path, "macroeconomic")
    if not matched:
        return jsonify({"error": "This path is not one of the endpoints in static/endpoints.json. Add it there first."}), 400
    endpoint_id, values = matched
    file = saved_file(endpoint_id, **values)
    same_base = (body.get("base") or API_BASE).rstrip("/") == API_BASE
    if file.exists() and same_base and not body.get("refresh"):
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    if same_base and not body.get("refresh") and (entry := known_no_data(endpoint_id, **values)):
        return no_data_answer(entry, "No data for this path")
    try:
        data, file = fetch_and_save(endpoint_id, base=body.get("base") or None, **values)
    except requests.HTTPError as e:
        return jsonify({"error": f"{e.response.status_code}: {e.response.text[:500]}"}), 502
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:  # missing key, network error, bad JSON...
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": saved_name(file), "from_cache": False})


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5001)), debug=True)
