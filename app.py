"""Minimal web viewer for Argaam API data.

Run:  python app.py   ->   http://127.0.0.1:5001
"""
import json
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory

from argaam_client import API_BASE, DATA_DIR, fetch_and_save

app = Flask(__name__, static_folder="static")

# Add new endpoints in this file as the project grows; the published page reads it too.
ENDPOINTS = json.loads((Path(app.static_folder) / "endpoints.json").read_text(encoding="utf-8"))


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify({"base": API_BASE, "endpoints": ENDPOINTS})


def cached(path, name):
    """Return data/<name>.json if it was saved before, otherwise fetch the path and save it."""
    file = DATA_DIR / f"{name}.json"
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    data, _ = fetch_and_save(path, name=name)
    return data


def lookup(path, name):
    """Serve a cached lookup list (used by the Group / Field dropdowns)."""
    try:
        return jsonify(cached(path, name))
    except requests.HTTPError as e:
        return jsonify({"error": f"{e.response.status_code}: {e.response.text[:300]}"}), 502
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/groups")
def groups():
    return lookup("/indicators/groups", "indicator_groups")


@app.get("/api/groups/<int:group_id>/fields")
def group_fields(group_id):
    return lookup(f"/indicators/groups/{group_id}/fields", f"indicators_groups_{group_id}_fields")


@app.post("/api/fetch")
def fetch_endpoint():
    body = request.get_json(force=True)
    path = body.get("path", "")
    if "{" in path:
        return jsonify({"error": "Fill in the {placeholders} in the path first."}), 400
    try:
        data, file = fetch_and_save(path, name=body.get("save_as"), base=body.get("base") or None)
    except requests.HTTPError as e:
        return jsonify({"error": f"{e.response.status_code}: {e.response.text[:500]}"}), 502
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:  # missing key, network error, bad JSON...
        return jsonify({"error": str(e)}), 500
    return jsonify({"data": data, "saved_to": str(file.name)})


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5001)), debug=True)
