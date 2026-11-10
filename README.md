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
argaam_client.py           # fetch(path) + save JSON to data/<api>/ (one request at a time, used by app.py)
argaam_downloader.py       # shared bulk download code for the fetch scripts: keys, proxy, pacing, retries, resume
fetch_indicator_groups.py  # script: pull /indicators/groups -> data/macroeconomic/indicator_groups.json
fetch_all_analyst_estimates.py  # script: every company's analyst estimates -> data/fundamentals/
app.py                     # web viewer server
static/index.html          # the whole UI
static/endpoints.json      # the one list of endpoints: API, Argaam path, and where each response is saved
data/                      # saved API responses (ready to push to a database), one folder per API,
                           # one subfolder per endpoint: data/<api>/<endpoint>/<values>.json
  macroeconomic/
    indicator_groups.json          # /indicators/groups
    indicator_fields/33.json       # /indicators/groups/33/fields
    indicator_values/33_125.json   # /indicators/groups/33/fields/125/values
  fundamentals/
    market_companies/3.json        # /markets/3/companies
    analyst_estimates/3_2222_year.json  # /companies/2222/analyst-estimates?marketId=3&period=year
    _progress.json                 # what the fetch script did with each item, and where it came from
.fetch_state/key_usage.json  # calls each API key used today, shared by all fetch scripts (not committed)
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
Saves every TASI and NOMU company (year and quarter) to `data/fundamentals/`, in the same files the Fundamentals tab reads. It uses `ARGAAM_API_KEYS` and the `DATA_IMPULSE_*` proxy settings from `.env`. Each response is saved as soon as it arrives, and running the script again continues where it stopped. Add `--dry-run` to see what is left, `--limit 5` for a small test, or `--refresh` to download everything again.

Two files track the work:
- `data/fundamentals/_progress.json` (committed) has one entry per company and period: `saved`, `no_data` (Argaam returned nothing) or `failed`, with the API base, path, parameters and fetch time. Saved and no-data entries are skipped on the next run; failed ones are tried again.
- `.fetch_state/key_usage.json` (not committed) counts the calls each key made today, shared by every fetch script. Keys are stored as a short fingerprint (part of a SHA-256 hash), never as the key itself, so reordering `ARGAAM_API_KEYS` keeps each count with the right key.

## Adding a new endpoint
Add one entry to `static/endpoints.json`, e.g.
```json
{"api": "fundamentals", "id": "analyst_estimates", "name": "Analyst estimates",
 "path": "/companies/{symbol}/analyst-estimates", "query": ["marketId", "period"],
 "file": "analyst_estimates/{marketId}_{symbol}_{period}",
 "description": "Analyst estimates for one company, yearly or quarterly"}
```
- `api` is the folder under `data/`.
- `path` is the Argaam path; `{placeholders}` are filled in with values.
- `query` lists values sent as `?name=value` instead of in the path.
- `file` is where a response is saved inside `data/<api>/` (without `.json`). Values may only contain letters, digits and `-`.

Python (`saved_file`, `fetch_and_save` in `argaam_client.py`, `endpoint_task` in `argaam_downloader.py`) and the page (`savedPath` in `index.html`) all read these templates, so no file name is typed by hand anywhere. Macroeconomic endpoints show up in the Macroeconomic tab's dropdown, and their paths can be edited there before fetching.

## Adding a new API tab
Add a button to `<nav id="tabs">` in `static/index.html` and a matching `<div id="tab-NAME" class="hidden">`. Call `display("NAME", response)` to show a response in the shared Fields / table / export section. Add the API's endpoints to `static/endpoints.json` with `"api": "NAME"`, and its responses are saved under `data/NAME/`.
