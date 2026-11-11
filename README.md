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
argaam_client.py           # shared basics: endpoints and file names, progress and key usage, single fetches for app.py
argaam_downloader.py       # shared bulk download code for the fetch scripts: keys, proxy, pacing, retries, resume
fetch_fundamentals.py      # script: every company's analyst estimates -> data/fundamentals/
fetch_macroeconomic.py     # script: every indicator group, field and series -> data/macroeconomic/
fetch_funds.py             # script: every fund manager, fund, fund details and price history -> data/funds/
fetch_ma.py                # script: every M&A deal list and deal record -> data/m&a/
fetch_projects.py          # script: every project list, project record and company's key developments -> data/projects/
app.py                     # web viewer server
static/index.html          # the whole UI
static/endpoints.json      # the one list of endpoints: API, Argaam path, and where each response is saved
data/                      # saved API responses (ready to push to a database), one folder per API,
                           # one subfolder per endpoint: data/<api>/<endpoint>/<values>.json
  macroeconomic/
    indicator_groups.json          # /indicators/groups
    indicator_fields/33.json       # /indicators/groups/33/fields
    indicator_values/33_125.json   # /indicators/groups/33/fields/125/values
    _progress.json                 # what the fetch script did with each item, and where it came from
  fundamentals/
    market_companies/3.json        # /markets/3/companies
    analyst_estimates/3_2222_year.json  # /companies/2222/analyst-estimates?marketId=3&period=year
    _progress.json                 # what the fetch script did with each item, and where it came from
  funds/
    fund_managers.json             # /funds/managers
    fund_movers.json               # /funds/movers
    manager_funds/2604.json        # /funds/managers/2604/funds
    fund_details/2604_2.json       # /funds/managers/2604/funds/2
    fund_history/2604_2.json       # /funds/managers/2604/funds/2/values/history?from=1980-01-01&to=<today>
    _progress.json                 # what was fetched, and where it came from
  m&a/
    market_deals/3.json            # /markets/3/mergers-acquisitions
    deal_details/720.json          # /markets/mergers-acquisitions/720
    _progress.json                 # what was fetched, and where it came from
  projects/
    projects_by_market/3.json      # /projects/by-market/3?page=1&pageSize=5000
    project_details/2269.json      # /projects/2269
    company_developments/2222.json # /companies/2222/developments
    _company_projects.json         # written by fetch_projects.py: each listed company and the saved projects that name it
    _progress.json                 # what was fetched, and where it came from
.fetch_state/key_usage.json  # calls each API key used today per endpoint, shared by the fetch scripts and the app (not committed)
.env                       # your API base + key (not committed)
EXPLAINED.md               # what data each endpoint returns, with real examples
API_EXAMPLES.md            # real questions answered with every API, and how to use the downloaded files
PROJECTS_API_SURPRISES.md  # surprises in the Projects & Capital Investments data, and what could be done about them
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

Start the web viewer and open http://127.0.0.1:5001 :
```
python app.py
```
Choose an endpoint, click **Fetch**, tick the fields you want, then **Export CSV** or **Export JSON**. Each fetch is also saved under `data/macroeconomic/`, and anything already saved loads from there until you click **Re-fetch from API**.

The **Fundamentals** tab fetches analyst estimates: pick a market, type a stock symbol (e.g. `2222`) and a period. The sandbox allows 5 requests a minute and 100 a day per endpoint, so a saved company loads from `data/fundamentals/` until you click **Re-fetch from API**. See `EXPLAINED.md` for what the data contains.

The **Investment funds** tab shows one fund's price history (a chart of the unit price, with the latest price, this year's and the last 12 months' return), its details (objective, strategy, fees, size), or this year's top-moving funds. Pick what to show, a fund manager and a fund. Saved funds load from `data/funds/`; choosing a manager or fund that isn't saved yet fetches it.

### Download all fundamentals data (analyst estimates)
```
python fetch_fundamentals.py
```
Saves every TASI and NOMU company (year and quarter) to `data/fundamentals/`, in the same files the Fundamentals tab reads. It uses `ARGAAM_API_KEYS` and the `DATA_IMPULSE_*` proxy settings from `.env`. Each response is saved as soon as it arrives, and running the script again continues where it stopped. Add `--dry-run` to see what is left, `--limit 5` for a small test, or `--refresh` to download everything again.

### Download all macroeconomic data
```
python fetch_macroeconomic.py --dry-run
python fetch_macroeconomic.py
```
Saves every indicator group, every group's fields and every field's values (the numbers over time) to `data/macroeconomic/`, in the same files the Macroeconomic tab reads. It works in three stages, because each list says what to fetch next:

1. `indicator_groups.json`: 1 call, the 29 main groups and their 301 sub-groups.
2. `indicator_fields/<groupId>.json`: 1 call per sub-group, its fields.
3. `indicator_values/<groupId>_<fieldId>.json`: 1 call per field, its values.

Start with `--dry-run`: it makes no calls and shows how many are left and about how many days that takes. A full download is about 5,300 calls (5,031 fields are known): about 3 days with 22 keys, because nearly all of them go to one endpoint (values), which gets 100 calls a day per key. The number of fields in groups whose field list isn't saved yet is estimated from the groups already saved. The script uses the same keys, proxy, flags (`--limit`, `--refresh`) and resume as the analyst estimates script. In the sandbox many fields return no data; those are recorded as `no_data` and skipped next time.

### Download investment funds data
```
python fetch_funds.py --dry-run
python fetch_funds.py --managers 2604 2501 2930
python fetch_funds.py
```
Saves fund managers, their funds, each fund's details and each fund's full price history to `data/funds/`, in the same files the Investment funds tab reads. Four stages, because each list says what to fetch next:

1. `fund_managers.json`: 1 call, the 46 fund managers. Also `fund_movers.json`, 1 call, this year's top 10 gainers and losers.
2. `manager_funds/<managerId>.json`: 1 call per manager, its funds.
3. `fund_details/<managerId>_<fundId>.json`: 1 call per fund, what it is and what it costs.
4. `fund_history/<managerId>_<fundId>.json`: 1 call per fund, every end-of-day unit price and net asset value since 1980 (in practice since the fund started).

`--managers` limits the run to some managers (IDs from `fund_managers.json`). A full download (done on 10 Nov 2026) is 499 funds from the 46 managers, two calls per fund (details and history), so about 1,050 calls. Since each endpoint has its own daily limit, it took about 10 minutes with 22 keys. 358 funds have prices (about 445,000 daily prices, 63 MB), and 356 of them are still priced in 2026, the same 356 that `fund_movers.json` ranks. Funds without prices (often closed ones) are recorded as `no_data`. The same keys, proxy, flags (`--dry-run`, `--limit`, `--refresh`) and resume as the other scripts. Use `--refresh` to get newer prices.

The **M&A & Transactions** tab shows every merger, acquisition and stake deal in a market (TASI or NOMU): tiles for the number of deals, disclosed values, the median and largest deal (in USD) and the share completed or cancelled, plus a chart of deals per year by status. Filter by type, status, year or company, or pick one deal to see its full record, including how it was financed. Saved data loads from `data/m&a/`.

### Download M&A data
```
python fetch_ma.py --dry-run
python fetch_ma.py --sample 15
python fetch_ma.py
```
Saves both markets' deal lists and every deal's full record to `data/m&a/`, in the same files the M&A & Transactions tab reads. Two stages, because the lists say which deals to fetch:

1. `market_deals/<marketId>.json`: 1 call per market, every deal in it. TASI (`3`) has 615 deals, NOMU (`14`) 19. Other markets answer HTTP 400.
2. `deal_details/<dealId>.json`: 1 call per deal, its full record, including how it was financed.

`--markets 14` limits the run to some markets, and `--sample N` fetches at most N new items per stage, picked to mix deal types and statuses. A full download (done on 11 Nov 2026) is 636 calls: 2 market lists and 634 deal records, all saved, none empty. Each endpoint has its own daily limit, so 22 keys (2,200 calls a day per endpoint) finished it in one run of about 7 minutes, 3.2 MB on disk. 392 deals say how they were financed: internal resources (281), loans (100), a capital increase (70) or a share swap (45); 242 don't say. The company endpoint (`/companies/{symbol}/mergers-acquisitions`) is not fetched: it returns the same records as the market list. The same keys, proxy, flags (`--dry-run`, `--limit`, `--refresh`) and resume as the other scripts. Use `--refresh` to pick up new deals.

The **Projects & Capital Investments** tab shows every capital project in a market (TASI or NOMU): tiles for the number of projects, disclosed and total cost (in riyals), the largest project and how many are under construction or completed, plus a chart of projects announced per year by status. Filter by status, country or year, pick one project to see its full record (owners, description, dates, capacity, updates), or pick a company to see its projects next to its key developments. Saved data loads from `data/projects/`.

### Download projects data
```
python fetch_projects.py --dry-run
python fetch_projects.py --sample 15
python fetch_projects.py
```
Saves both markets' project lists, every project's full record and every listed company's key developments to `data/projects/`, in the same files the Projects & Capital Investments tab reads. Three stages:

1. `projects_by_market/<marketId>.json`: 1 call per market, every project in it, as one page of up to 5,000 rows (the API's default page is 10). TASI (`3`) has 1,696 projects in 3,396 rows (a project repeats once per company), NOMU (`14`) 310; 40 are in both.
2. `project_details/<projectId>.json`: 1 call per project, its full record: owners and related companies, category, description, updates, dates, capacity.
3. `company_developments/<symbol>.json`: 1 call per company in `data/fundamentals/market_companies/` (417 on TASI and NOMU), its dated key developments.

After stage 2 the script writes `_company_projects.json`, which the tab's company view reads; `--index` rebuilds it without any calls. `--markets 14` limits the run to some markets, `--symbols 2222 2082` the developments to some companies, and `--sample N` fetches at most N new items per stage, picked to mix markets, statuses and projects with and without a cost. A full download (done on 11 Nov 2026) is 2,385 calls: 2 market lists, 1,966 project records and 417 development lists. Each endpoint has its own daily limit, so 22 keys (2,200 calls a day per endpoint) finished it in one run of about 27 minutes, 19 MB on disk. Every project record was saved; 416 companies have key developments (3,608 in all), and `9551` has none (HTTP 404). 225 listed companies are named in at least one project, most of all ACWA (116), SABIC (100) and Saudi Aramco (85). Costs are in millions of riyals. See `PROJECTS_API_SURPRISES.md` for what to watch for in this data. The company endpoint (`/projects/by-company/{symbol}`) is not fetched: its rows are in the market lists, and each project record names its companies. The same keys, proxy, flags (`--dry-run`, `--limit`, `--refresh`) and resume as the other scripts.

### How fetches are tracked
Two files, the same for every API. The fetch scripts and the web app both write to them, so a company fetched in the browser counts against the key's quota and is skipped by the next script run:
- `data/<api>/_progress.json` (committed) has one entry per item: `saved`, `no_data` (Argaam returned nothing) or `failed`, with the API base, path, parameters and fetch time. Saved and no-data entries are skipped on the next run; failed ones are tried again. Entries marked `"backfilled": true` were filled in from files saved before this file existed.
- `.fetch_state/key_usage.json` (not committed) counts the calls each key made today **per endpoint**, shared by every fetch script and the app. Argaam's limit of 100 calls a day counts each endpoint separately: a key that used 100 `indicator_values` calls can still make 100 `fund_history` calls that day. A key stops for an endpoint when Argaam says none are left for it. Keys are stored as a short fingerprint (part of a SHA-256 hash), never as the key itself, so reordering `ARGAAM_API_KEYS` keeps each count with the right key.

When something is recorded as `no_data`, the web app answers from the progress file instead of calling Argaam again, and says when it was checked. **Re-fetch from API** always asks again.

## The standard for every API
Fundamentals, Macroeconomic, Investment funds, M&A & Transactions and Projects & Capital Investments follow the same pattern, and a new Argaam API should too:

| What | Where | Same for every API? |
|------|-------|---------------------|
| Its endpoints | entries in `static/endpoints.json` with `"api": "<api>"` | yes, the same fields |
| Saved responses | `data/<api>/<endpoint>/<values>.json`, from each entry's `file` template | yes |
| What happened to each item | `data/<api>/_progress.json` (committed) | yes |
| Calls each key used today, per endpoint | `.fetch_state/key_usage.json` (shared by all APIs) | yes, one file |
| How to fetch (keys, proxy, pacing, retries, resume) | `argaam_downloader.py` | yes, shared code |
| What to fetch | one script per API (`fetch_macroeconomic.py`, `fetch_fundamentals.py`, `fetch_funds.py`, `fetch_ma.py`, `fetch_projects.py`): the list of items, often in stages where one list says what to fetch next | no, each API has its own |
| Docs | a "Download all ..." section here, the endpoint in `EXPLAINED.md`, examples in `API_EXAMPLES.md` | yes |

Every fetch script takes `--dry-run` (calls left and about how many days, no calls made), `--limit N` and `--refresh`.

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

Python (`saved_file`, `endpoint_task` and `fetch_and_save` in `argaam_client.py`) and the page (`savedPath` in `index.html`) all read these templates, so no file name is typed by hand anywhere. Macroeconomic endpoints show up in the Macroeconomic tab's dropdown, and their paths can be edited there before fetching.

## Adding a new API tab
Add a button to `<nav id="tabs">` in `static/index.html` and a matching `<div id="tab-NAME" class="hidden">`. Call `display("NAME", response)` to show a response in the shared Fields / table / export section. Add the API's endpoints to `static/endpoints.json` with `"api": "NAME"`, and its responses are saved under `data/NAME/`.
