---
name: add-argaam-api
description: Add a new Argaam API to this project end to end - choose its most important endpoints from the Argaam docs page, write fetch_<api>.py (all keys + proxies, progress file), add a tab in the API viewer (local and GitHub Pages), pull a small sample, write EXPLAINED.md / API_EXAMPLES.md / README docs, and only after the user approves, pull all the data. Use when the user gives an Argaam API docs link or asks to add, onboard or fetch a new Argaam API.
---

# Add a new Argaam API

The user gives a link to an Argaam API's docs page (the page that lists each endpoint and what it returns). You turn it into a fully working API in this project, following the same standard as `macroeconomic`, `fundamentals` and `funds` (README section "The standard for every API").

**Work in baby steps and stop at every gate (🛑).** The user wants to follow along and approve before anything big happens. Keep the task list updated per phase.

**Never commit or push without asking each time.** "Publish it" or "put it on GitHub Pages" is not permission. Ask, and wait for a yes.

## What every API gets (the deliverables)

| # | Deliverable | Where |
|---|-------------|-------|
| 1 | Endpoints, with `api`, `id`, `name`, `path`, `query`, `file`, `description` | `static/endpoints.json` |
| 2 | A tab with the API's name that shows and visualizes its data, locally **and** on GitHub Pages | `static/index.html` (+ a route in `app.py`) |
| 3 | All the data, saved locally | `data/<api>/<endpoint_id>/<values>.json` (an endpoint without parameters: `data/<api>/<endpoint_id>.json`) |
| 4 | One Python fetch script that uses every key and the proxies | `fetch_<api>.py`, built on `argaam_downloader.py` |
| 5 | A progress file, one per API | `data/<api>/_progress.json` (written by `Progress(DATA_DIR / "<api>")`) |
| 6 | What the data is: each endpoint, its fields, an example, what to watch for | a new section in `EXPLAINED.md` |
| 7 | Examples to try in the viewer | a new section in `API_EXAMPLES.md` |
| 8 | How to run it | a "Download … data" section in `README.md`, plus the script name in the standard table |

`<api>` is a short lowercase folder name (`funds`, `macroeconomic`). The tab label is the API's name as Argaam writes it, e.g. "Investment funds".

## Phase 1: read the docs and propose a plan

1. Open the docs link in the built-in browser (`preview_start` with the `url`) and read it with `get_page_text`. If it shows a sign-in page, ask the user to sign in there, then carry on. Read every endpoint: its path, parameters, what it returns, and whether it is paginated or limited by dates.
2. Read the existing setup so that you copy it rather than reinvent it: `fetch_funds.py` (the best template: stages, `--dry-run` estimate, budget), `argaam_downloader.py` (`make_slots`, `fetch_one`, `run_tasks`, `calls_left`, `DAILY_LIMIT`, `stop`), `argaam_client.py` (`endpoint_task`, `Progress`, `KeyUsage`, `saved_file`, `fetch_and_save`), the `funds` route in `app.py`, and the Investment funds tab in `static/index.html`.
3. **Decide what matters most.** Rank the endpoints by how useful their data is: core reference lists and the data people actually analyse (prices, financials, history) come first. Skip endpoints that duplicate another one or only repeat data from another API already in the project. Note which list feeds which endpoint, since that decides the **stages** (for example managers → their funds → each fund's details).
4. Make a few real calls to check what the docs don't say: the shape of each response, its IDs, and roughly how many items each list has. Use `fetch_and_save` through a short Python one-off with the sandbox key, a handful of calls at most. They count against quota, and saved responses land in `data/<api>/` anyway.
5. Estimate the full size: number of calls per stage and days with the current keys. Remember that Argaam's daily limit counts **each endpoint separately**, 100 calls per key.

🛑 **Gate 1: show the plan and wait.** In plain words, give:
- the endpoints you chose, in order, each with one line on what it gives, and the ones you are skipping and why;
- the stages (which list feeds which);
- the folder name, the tab name, and what the tab will show (which views, charts or tables);
- the estimated calls and days for the full pull.

Ask the user to confirm or change it. Don't build anything yet.

## Phase 2: build, then pull a sample

1. **Endpoints:** add the entries to `static/endpoints.json` (see README "Adding a new endpoint"). Filled-in values may contain only letters, digits and `-`.
2. **Fetch script `fetch_<api>.py`:** model it on `fetch_funds.py`:
   - a module docstring listing the stages and the run commands;
   - it decides only *what* to fetch, while `argaam_downloader.py` does the *how* (keys, proxy, pacing, retries, saving, progress);
   - the flags `--dry-run`, `--limit N`, `--refresh`, plus **`--sample N`: at most N new items per stage**, so a sample covers every stage;
   - any filters the API needs (like `--managers`);
   - a `--dry-run` that makes no calls and prints what's left per stage, the calls left today per endpoint, and about how many days;
   - every response saved as it arrives, and a rerun continues where it stopped (`left()` skips saved and `no_data` items).
3. **App route:** add `/api/<api>/<endpoint_id>` to `app.py`, like the `funds` route: it reuses the saved copy unless `refresh=1`, answers `no_data` from progress, and calls `fetch_and_save` otherwise.
4. **Tab:** add a `<button data-tab="<api>">` to `<nav id="tabs">` and a `<div id="tab-<api>" class="hidden">`, following the Investment funds tab:
   - dropdowns built from the saved lists, and a show/fetch control;
   - stat tiles for the key numbers;
   - a chart for anything over time; read the `dataviz` skill before drawing charts;
   - `display("<api>", rows)` for the shared table and export.

   It must work in both modes:
   - **Local** (Flask) calls the route.
   - **Published** (GitHub Pages, no server) reads only saved files: check `savedFiles.has(savedPath(...))`, list only items that were fetched, and remove the refresh button.
5. **Sample:** run `python fetch_<api>.py --dry-run`, then `python fetch_<api>.py --sample 15` (10–20 items per stage; pick a mix that shows the variety, e.g. different types or markets, using filters if the script has them). The sample goes into the real `data/<api>/` folder and progress file, so the full run later skips it and no calls are wasted.
6. **Check the tab:**
   - Locally: `preview_start` with `{name: "app"}` and open the new tab. Click through every view, read the console for errors, and take a screenshot.
   - Published version: build `_site` the same way `.github/workflows/static.yml` does, in the scratchpad: copy `static/` and `data/`, then write `saved_files.json` with the same one-liner. Point the `published-preview` entry in `.claude/launch.json` at that folder, start it, and check the tab again.
7. **Docs:** write the `EXPLAINED.md` section (each endpoint: what it returns, its fields, a short real example from the sample, what to watch for, in practice), the `API_EXAMPLES.md` section (numbered examples continuing the existing numbering, each one a real question answered step by step in the new tab, using items that exist in the sample), and the README "Download … data" section with the run commands and stages. In the README "Project Structure" block, add the `fetch_<api>.py` line and a `data/<api>/` entry with one example file per endpoint, like `funds/`. In the standard table, add the script to the "What to fetch" row, and update the "three APIs" wording wherever it appears.

🛑 **Gate 2: show the sample and wait for approval of the full pull.** Show:
- screenshots of the tab, locally and in the published preview;
- what the sample holds, per stage: saved / no data / failed;
- anything surprising in the data (empty fields, odd units, missing history);
- the `--dry-run` numbers for the full pull: calls per stage, calls left today, about how many days;
- the docs you wrote.

Ask: "Pull all the data?" Don't start the full pull without a clear yes. The user may first want changes to the UI, the endpoints or the docs; make them and show again.

## Phase 3: the full pull (only after approval)

1. Run `python fetch_<api>.py` in the background (`run_in_background`), because it can take a long time. If it needs more than one day of quota, say so. The user reruns the same command the next day and it resumes.
2. When it ends, report: per stage saved / no data / failed, rows where it makes sense, the size on disk (`du -sh data/<api>`), and anything left to fetch. Rerun once for `failed` items if there are a few.
3. Check sizes for GitHub: no single file over 100 MB (`find data/<api> -size +90M`), and warn if `data/` grows past about 1 GB, the Pages site limit.
4. Update the README section with the real totals (like the funds section: how many items, calls, how long it took).

## Phase 4: hand off

- Rebuild the published preview and check the tab once more with the full data.
- Summarize what was added: files, tab, data counts.
- 🛑 Ask before committing, and separately before pushing. Pushing to `main` is what puts the tab and its data on GitHub Pages. Suggested commits, like earlier APIs: (1) the API, script and tab; (2) the sample/full data. Each message ends with the attribution line the session gives.

## Pitfalls already met in this project

- The daily limit is per endpoint, per key. Estimate days per endpoint, not for the total.
- Some items return nothing: they are recorded as `no_data` and not retried, which is correct. Mention them in "What to watch for".
- Date-range endpoints: use a very early `from` date to get the full history (funds use `1980-01-01`).
- File names come from the `file` template only. Never type a path by hand in Python or JS.
- `_progress.json` is committed, `.fetch_state/` is not. Files starting with `_` are left out of `saved_files.json`.
