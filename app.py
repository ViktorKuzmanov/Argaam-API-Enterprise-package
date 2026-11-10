"""Minimal web viewer for Argaam API data.

Run:  python app.py   ->   http://127.0.0.1:5001
"""
import json
import os
import re

import requests
from flask import Flask, jsonify, request, send_from_directory

from argaam_client import API_BASE, ENDPOINTS, fetch_and_save, match_path, saved_file, saved_name

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
    if file.exists() and request.args.get("refresh") != "1":
        return jsonify({"data": json.loads(file.read_text(encoding="utf-8")), "saved_to": saved_name(file), "from_cache": True})
    try:
        data, file = fetch_and_save("analyst_estimates", **values)
    except requests.HTTPError as e:
        return upstream_error(e)
    except LookupError:
        return jsonify({"error": f"No analyst estimates for symbol {symbol} on this market."}), 404
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
