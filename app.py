"""Minimal web viewer for Argaam API data.

Run:  python app.py   ->   http://127.0.0.1:5001
"""
import requests
from flask import Flask, jsonify, request, send_from_directory

from argaam_client import API_BASE, fetch_and_save

# Add new endpoints here as the project grows.
ENDPOINTS = [
    {"name": "Indicator groups", "path": "/indicators/groups", "save_as": "indicator_groups"},
    {"name": "Indicator group fields", "path": "/indicators/groups/{groupId}/fields", "save_as": None},
    {"name": "Indicator series", "path": "/indicators/groups/{groupId}/fields/{fieldId}/values", "save_as": None},
]

app = Flask(__name__, static_folder="static")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify({"base": API_BASE, "endpoints": ENDPOINTS})


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
    app.run(port=5001, debug=True)
