# Argaam API Enterprise Package

A minimal tool that pulls data from the Argaam REST APIs with Python, saves every response as a local `.json` file, and shows it in a simple web page where you pick fields, preview them in a table, and export CSV/JSON.

## Technology Stack & Dependencies

- Python 3
- virtualenv (.venv)
- pip (Python package installer)
- requests (HTTP calls to the API)
- python-dotenv (loads `.env`)
- Flask (tiny local web server for the viewer)

## Project Structure

```
argaam_client.py           # fetch(path) + save JSON to data/
fetch_indicator_groups.py  # script: pull /indicators/groups -> data/indicator_groups.json
app.py                     # web viewer server (list of endpoints lives here)
static/index.html          # the whole UI
data/                      # saved API responses (ready to push to a database)
.env                       # your API base + key (not committed)
EXPLAINED.md               # what data each endpoint returns, with real examples
```

### 1. Clone/Download the Repository

### 2. Create and activate the virtual environment
```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```
python -m pip install -r requirements.txt
```

### 4. Set your API key
Copy `.env.example` to `.env` (if it doesn't exist) and fill in:
```
ARGAAM_API_BASE=https://api-sandbox.argaam.com/api/v1.1
ARGAAM_SANDBOX_API_KEY=your_sandbox_api_key_here
```
The key is sent in the `apikey` header.

### 5. Run the project

Pull indicator groups from the command line (saves `data/indicator_groups.json`):
```
python fetch_indicator_groups.py
```

Or start the web viewer and open http://127.0.0.1:5001 :
```
python app.py
```
Choose an endpoint, click **Fetch**, tick the fields you want, then **Export CSV** or **Export JSON**. Each fetch is also saved under `data/`.

## Adding a new endpoint
Add one line to `ENDPOINTS` in `app.py`, e.g.
```python
{"name": "Indicator series", "path": "/indicators/groups/{groupId}/fields/{fieldId}/values", "save_as": None},
```
Paths with `{placeholders}` can be edited in the UI before fetching.
