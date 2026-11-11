# Projects & Capital Investments API: surprises in the data

Notes for later work on the **Projects & Capital Investments API** (`fetch_projects.py`, `data/projects/`, the "Projects & Capital Investments" tab).
Found on 11 Nov 2026 while pulling the data from the Argaam sandbox (2 market lists, all 1,966 project records, 416 companies' key developments). Numbers are from the full pull.
For the full field descriptions, see the "Projects & Capital Investments" section in `EXPLAINED.md`.

Each item says what we saw, an example, what the tab does about it today, and what could still be done.

---

## 1. Costs have no unit, but they are millions of riyals

- **Seen:** `cost` is a bare number. Nothing in the market list says what unit it is in.
- **Example:** NEOM (`749`) has `cost: 1875000`. NEOM was announced at $500 billion, and 500,000 × 3.75 = 1,875,000, so this is **millions of riyals**. The project record agrees: `measuringUnitID: 3`, `costCurrencyID: 3`, and the same number.
- **Today:** the tab shows costs as SAR millions or billions (e.g. "SAR 56m", "SAR 1,875bn"), and the table column is called `costSarMillions`.
- **Could do:** ask Argaam which units the IDs `measuringUnitID` and `costCurrencyID` stand for, in case some projects use another unit or currency.

## 2. Most projects have no cost

- **Seen:** only 742 of 1,696 TASI projects (44%) and 98 of 310 NOMU projects (32%) have a cost. New projects rarely have one.
- **Today:** the tiles say how many projects have a cost ("Cost disclosed"), and totals only add up the known costs.
- **Could do:** nothing in the data; just never read "total cost" as the whole market.

## 3. NEOM is marked "Completed"

- **Seen:** NEOM (`749`) has status `Completed` and expected completion `2024`.
- **Likely meaning:** the status describes Argaam's record (for example, the announcement), not whether the project is built. Other "Completed" mega-projects may be the same.
- **Today:** shown as Argaam gives it.
- **Could do:** be careful with "Completed" counts for very large projects; check a few more (Diriyah Gate `715` is also "Completed").

## 4. The market lists repeat projects

- **Seen:** the TASI list has 3,396 rows but only 1,696 different projects. A project appears once per company it involves, in rows that are exactly the same.
- **Today:** the tab and `fetch_projects.py` count each project once.
- **Could do:** anyone using `projects_by_market/*.json` directly (e.g. loading it into a database) must remove the repeats by `projectID` first.

## 5. NOMU's list contains TASI projects too

- **Seen:** 40 projects are in both the TASI and NOMU lists. Example: `2347`, an Academy of Learning school (Academy of Learning is on NOMU), whose owner is a TASI-listed company.
- **Today:** each market view shows its own list, so those 40 are counted in both.
- **Could do:** when adding both markets together, count each `projectID` once (1,966 different projects, not 2,006).

## 6. Some projects have no English name

- **Seen:** 11 projects have `projectNameEn: null`, only the Arabic name. Example: `2349`, BAHRI's two container and ro-ro ships ("ناقلتي حاويات وبضائع مدحرجة").
- **Today:** the tab shows the Arabic name for them.

## 7. Start dates are written in a code

- **Seen:** in the market list, `startDate` looks like `0-2017`, `7-2026` or `NYD`:
  - `0-2017`: only the year is known (2017);
  - `7-2026`: a quarter, stored as its first month (the project record says "Q3 2026"); `1-2027` is Q1 2027;
  - `NYD`: not yet decided. 557 TASI projects have `NYD` as start, 378 as completion.
- **Today:** the tab turns them into "2017", "Q3 2026" and "not yet decided".
- **Could do:** check whether other months than 1, 4, 7 and 10 ever appear (the tab shows them as `2026-05` if they do).

## 8. In the project record, `startDate` is a placeholder

- **Seen:** when only the year is known, the record's `startDate` says `December <year>` (e.g. "December 2026"). It is not a real month.
- **Today:** the tab uses `startingDateForProjectDetailEn` instead ("2026", "Q3 2026"), which is what Argaam shows on its site.
- **Could do:** never use `startDate` from `project_details` for analysis.

## 9. The project record has less than Argaam's docs promise

- **Seen:** the docs say a project record has "budget breakdown, timeline, and milestones". The sandbox has none of them. The only timeline is the start and completion text, plus dated updates written inside `commentsEn` (HTML).
- **Could do:** ask Argaam whether the production API has these fields. If milestones are needed, they would have to be read out of the `commentsEn` text.

## 10. Categories are rough

- **Seen:** many projects are `Other`, some names end with a space (`"Industry "`), and a ready-meals factory (`2336`) is filed under `Real Estate`.
- **Could do:** treat categories as a hint only, or make our own.

## 11. Many named companies aren't listed, and their market is wrong

- **Seen:** project records name 1,019 companies that are not listed on TASI or NOMU: private companies, subsidiaries, even `AlRiyadh Municipality`. Most of them still have `marketNameEn: "TASI"`. A few say `Dubai`, `Abu Dhabi` or `Muscat`.
- **Today:** the company view lists only the 417 listed companies (matched by `companyID`), so unlisted ones can't be picked there.
- **Could do:** never trust `marketNameEn`; check `companyID` against `data/fundamentals/market_companies/`. A view of the biggest unlisted partners could be added.

## 12. Key developments: dates without a month or day

- **Seen:** of 3,608 developments, 708 have no month and 817 no day (`developmentMonth` / `developmentDay` are null). `fullDate` then shows a made-up month and day.
- **Example:** Aramco's 1933 oil concession has only the year.
- **Today:** the tab shows only what is known ("1933", "2023-03" or "2023-03-23") and never uses `fullDate`.

## 13. Key developments: no text body, and it is company history, not news

- **Seen:** `bodyEn` / `bodyAr` are always empty (all 3,608); only the title and the link to the Argaam article are filled. Most companies have 2 to 15 developments, 8 is typical (founding, capital increases, listings, renames). Aramco has the most, 39, back to 1933. `9551` answers 404 and 6 companies an empty list.
- **Also:** `marketId` in the answer is always `0`, and the list is not in date order (the tab sorts it).

## 14. The company endpoint was skipped

- **Seen:** `/projects/by-company/{symbol}` returned 85 projects for Aramco, all already in the market lists, and without the company's role. Our own company list (built from the project records) also finds exactly 85 for Aramco, so nothing is lost.
- **Today:** not fetched. The company view uses `_company_projects.json` instead, built by `fetch_projects.py` from the saved project records (owner or related company).
- **Could do:** if we need projects where a company is a contractor or consultant (the docs mention those roles), fetch this endpoint after all: 417 calls, one day.
