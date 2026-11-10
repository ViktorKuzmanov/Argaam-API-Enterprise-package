# [Argaam API Enterprise Package](https://viktorkuzmanov.github.io/Argaam-API-Enterprise-package/)

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
argaam_client.py           # fetch(path) + save JSON to data/<api>/
fetch_indicator_groups.py  # script: pull /indicators/groups -> data/macroeconomic/indicator_groups.json
fetch_all_analyst_estimates.py  # script: every company's analyst estimates -> data/fundamentals/
app.py                     # web viewer server (list of endpoints lives here)
static/index.html          # the whole UI
data/                      # saved API responses (ready to push to a database), one folder per API:
  macroeconomic/           #   indicator groups, group fields, indicator series (/indicators/...)
  fundamentals/            #   analyst estimates and company lists (/companies/..., /markets/...)
.env                       # your API base + key (not committed)
EXPLAINED.md               # what data each endpoint returns, with real examples
API_EXAMPLES.md            # one real question answered with all three endpoints
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

Pull indicator groups from the command line (saves `data/macroeconomic/indicator_groups.json`):
```
python fetch_indicator_groups.py
```

Or start the web viewer and open http://127.0.0.1:5001 :
```
python app.py
```
Choose an endpoint, click **Fetch**, tick the fields you want, then **Export CSV** or **Export JSON**. Each fetch is also saved under `data/macroeconomic/`, and anything already saved loads from there until you click **Re-fetch from API**.

The **Fundamentals** tab fetches analyst estimates: pick a market, type a stock symbol (e.g. `2222`) and a period. The sandbox allows 5 requests a minute and 100 a day per endpoint, so a saved company loads from `data/fundamentals/` until you click **Re-fetch from API**. See `EXPLAINED.md` for what the data contains.

### Download all analyst estimates
```
python fetch_all_analyst_estimates.py
```
Saves every TASI and NOMU company (year and quarter) to `data/fundamentals/`, in the same files the Fundamentals tab reads. It uses `ARGAAM_API_KEYS` and the `DATA_IMPULSE_*` proxy settings from `.env`. Each response is saved as soon as it arrives, and running the script again continues where it stopped. Add `--dry-run` to see what is left, `--limit 5` for a small test, or `--refresh` to download everything again. Progress is kept in `.fetch_state/`, which is not committed.

## Adding a new API tab
Add a button to `<nav id="tabs">` in `static/index.html` and a matching `<div id="tab-NAME" class="hidden">`. Call `display("NAME", response)` to show a response in the shared Fields / table / export section. Save that API's responses in their own folder: add a `NAME_DIR = DATA_DIR / "NAME"` next to `MACRO_DIR` and `FUNDAMENTALS_DIR` in `argaam_client.py` and pass it to `fetch_and_save`.

## Adding a new endpoint
Add one line to `ENDPOINTS` in `app.py`, e.g.
```python
{"name": "Indicator series", "path": "/indicators/groups/{groupId}/fields/{fieldId}/values", "save_as": None},
```
Paths with `{placeholders}` can be edited in the UI before fetching.
