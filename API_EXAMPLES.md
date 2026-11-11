# API Examples

Real examples you can try in the app. Examples 1 to 3 use the three indicator endpoints, step by step. Examples 4 to 13 use analyst estimates from both markets. Examples 14 to 21 use investment funds, 22 to 26 use M&A deals, and 27 to 32 use capital projects. Every response below is a real response from the sandbox.

## How to try it

Run `python app.py`, open http://127.0.0.1:5001, paste each path below into the **Path** box and click **Fetch**.

---

## Example 1: How big is the economy?

### The question

> **"How big is Saudi Arabia's economy?"**

An analyst wants Saudi GDP, the total value of everything the country produces in a year. They don't know the IDs yet, so they find them one step at a time:

```
1. Which topics exist?               → "National Accounts" → groupId = 33
2. What is inside National Accounts? → "GDP"               → fieldId = 125
3. Give me the number                → 2026 = 4431
```

---

### Step 1: Find the topic

```
/indicators/groups
```

**What you get:** the list of all topics (names and IDs, no numbers).

```json
[
  { "groupID": 17, "nameEn": "Macro", "subGroups": [
      { "groupID": 33,  "nameEn": "National Accounts" },
      { "groupID": 277, "nameEn": "GDP Growth Rates (%)" }
  ]},
  { "groupID": 197, "nameEn": "Unemployment", "subGroups": [ ... ] }
]
```

GDP is a whole-economy number, so it sits under **Macro → National Accounts**. That gives you **`groupId = 33`**.

### Step 2: Find the indicator

```
/indicators/groups/33/fields
```

**What you get:** the indicators inside National Accounts (names and IDs, no numbers).

```json
[
  { "fieldID": 58,  "displayNameEn": "Population" },
  { "fieldID": 59,  "displayNameEn": "GDP per capita" },
  { "fieldID": 125, "displayNameEn": "Gross Domestic Product at Current Prices (Base year 2010)" },
  { "fieldID": 170, "displayNameEn": "Debt to GDP" }
]
```

GDP is **`fieldId = 125`**.

### Step 3: Get the number

```
/indicators/groups/33/fields/125/values
```

**What you get:** the actual data, one entry per year or period.

```json
{
  "economicIndicatorFieldID": 125,
  "displayNameEn": "Gross Domestic Product at Current Prices (Base year 2010)",
  "values": [
    { "year": 2026, "fiscalPeriodTypeID": 4, "fiscalPeriodID": 1, "value": 4431 }
  ]
}
```

**Answer:** Saudi GDP for 2026 is **4431**, most likely in billions of SAR. The API doesn't state the unit, so check Argaam's docs before using the number in a report.

---

## Example 2: Is the economy growing?

### The question

> **"How fast did Saudi Arabia's economy grow this year?"**

A reporter wants the real GDP growth rate, which is growth with inflation removed. That's the number news outlets quote ("the economy grew 3.5%"):

```
1. Which topics exist?               → "National Accounts"       → groupId = 33
2. What is inside National Accounts? → "GDP Growth (Chain-Linked)" → fieldId = 128
3. Give me the number                → 2026 = 3.5
```

### Step 1: Find the topic

```
/indicators/groups
```

**What you get:** the same topic list as in Example 1. Growth is a whole-economy number, so it's under **Macro → National Accounts**. That gives you **`groupId = 33`**.

### Step 2: Find the indicator

```
/indicators/groups/33/fields
```

**What you get:** the indicators inside National Accounts. There are two growth figures:

```json
[
  { "fieldID": 127, "displayNameEn": "GDP Growth at Current Prices" },
  { "fieldID": 128, "displayNameEn": "GDP Growth at Chain-Linked Methodology" }
]
```

"Current prices" includes inflation. "Chain-linked" removes inflation, so it shows real growth. You want real growth, so that's **`fieldId = 128`**.

### Step 3: Get the number

```
/indicators/groups/33/fields/128/values
```

**What you get:**

```json
{
  "economicIndicatorFieldID": 128,
  "displayNameEn": "GDP Growth at Chain-Linked Methodology",
  "values": [
    { "year": 2026, "fiscalPeriodTypeID": 4, "fiscalPeriodID": 1, "value": 3.5 }
  ]
}
```

**Answer:** the Saudi economy grew **3.5%** in real terms in 2026.

---

## Example 3: Is the government spending more than it earns?

### The question

> **"Will the Saudi government run a deficit in 2026?"**

A business owner who sells to government agencies wants to know if the state budget is tight this year. If spending is higher than revenue, the government has a deficit and may cut or delay projects.

```
1. Which topics exist?                     → "Govt Budget" (50) → sub-group "Public Budget Estimates" → groupId = 51
2. What is inside Public Budget Estimates? → "Expected Surplus (Deficit)" → fieldId = 105
3. Give me the number                      → 2026 = -165
```

### Step 1: Find the topic

```
/indicators/groups
```

**What you get:** the topic list. This time the topic is under **Govt Budget**:

```json
{ "groupID": 50, "nameEn": "Govt Budget", "subGroups": [
    { "groupID": 51,  "nameEn": "Public Budget Estimates" },
    { "groupID": 52,  "nameEn": "Actual Revenue & Expenditure" },
    { "groupID": 53,  "nameEn": "Public Debt" }
]}
```

There are two levels here:

- **Govt Budget (`50`)** is a **main group**. It is only a folder that holds related tables.
- **Public Budget Estimates (`51`)** is a **sub-group** inside it. This is the actual table with the indicators.

The next step needs the **sub-group** ID. `/indicators/groups/50/fields` returns no data (HTTP 204), and `/indicators/groups/51/fields` returns the indicators.

They want the plan for this year, not past results, so they pick **Public Budget Estimates → `groupId = 51`**.

### Step 2: Find the indicator

```
/indicators/groups/51/fields
```

**What you get:** the five indicators in the budget plan:

```json
[
  { "fieldID": 103, "displayNameEn": "Total Revenues" },
  { "fieldID": 104, "displayNameEn": "Total Expenditures" },
  { "fieldID": 105, "displayNameEn": "Expected Surplus (Deficit)" },
  { "fieldID": 297, "displayNameEn": "Oil Revenue" },
  { "fieldID": 298, "displayNameEn": "Other Revenues" }
]
```

The surplus or deficit answers the question directly, so **`fieldId = 105`**.

### Step 3: Get the number

```
/indicators/groups/51/fields/105/values
```

**What you get:**

```json
{
  "economicIndicatorFieldID": 105,
  "displayNameEn": "Expected Surplus (Deficit)",
  "values": [
    { "year": 2026, "fiscalPeriodTypeID": 4, "fiscalPeriodID": 1, "value": -165 }
  ]
}
```

**Answer:** yes. The minus sign means a deficit of **165** (most likely billion SAR). To see why, fetch fields `103` and `104` the same way: revenue is **1147** and spending is **1313**.

---

## Using the downloaded macroeconomic files

After `python fetch_macroeconomic.py`, every series is a file in `data/macroeconomic/indicator_values/`, named `<groupId>_<fieldId>.json`. This turns all of them into one table, ready for a spreadsheet or a database:

```python
import json, pathlib

rows = []
for file in sorted(pathlib.Path("data/macroeconomic/indicator_values").glob("*.json")):
    series = json.loads(file.read_text(encoding="utf-8"))
    for point in series["values"]:
        rows.append({"field": series["displayNameEn"], "year": point["year"], "value": point["value"]})
```

With the three series saved today, `rows` holds the answers to Examples 1 to 3:

```
{'field': 'Gross Domestic Product at Current Prices (Base year 2010)', 'year': 2026, 'value': 4431}
{'field': 'GDP Growth at Chain-Linked Methodology', 'year': 2026, 'value': 3.5}
{'field': 'Expected Surplus (Deficit)', 'year': 2026, 'value': -165}
```

To see what has been downloaded so far, and what Argaam had no data for, open `data/macroeconomic/_progress.json`: each entry's `status` is `saved`, `no_data` or `failed`.

---

## Analyst estimates examples

### How to try them

Open the **Fundamentals** tab, enter the **Market**, **Stock symbol** and **Period** shown in the example, then click **Fetch**. The data is already saved, so this uses no API calls.

You get one row per broker, per metric, per period. This is one real row from Example 4, shortened:

```json
{
  "fsFieldNameEn": "IS Net Income",
  "companyNameEn": "Saudi Arabian Oil Co.",
  "forYear": 2029,
  "fiscalPeriodValue": "YEAR",
  "value": 560966.0,
  "brokerID": 3939
}
```

To answer each question, find the rows with the year and metric it names. Values appear to be in millions of SAR, but the API doesn't state the unit.

| Example | Market | Symbol | Period | Company |
|---------|--------|--------|--------|---------|
| 4 | TASI | `2222` | Annual | Saudi Aramco |
| 5 | TASI | `1120` | Annual | Al Rajhi Bank |
| 6 | TASI | `7010` | Annual | Saudi Telecom |
| 7 | TASI | `2280` | Annual | Almarai |
| 8 | TASI | `4190` | Annual | Jarir Marketing |
| 9 | TASI | `2010` | Quarterly | SABIC |
| 10 | NOMU | `9522` | Annual | Alhasoob |
| 11 | NOMU | `9626` | Annual | Basma Adeem Medical |
| 12 | NOMU | `9570` | Annual | Tam Development |
| 13 | NOMU | `9615` | Annual | Mufeed |

---

## TASI examples

### Example 4: Saudi Aramco's expected profit

> **"How much do analysts expect Aramco to earn in 2026?"**

**Enter:** TASI, `2222`, Annual
**Find:** `forYear` = 2026 and `fsFieldNameEn` = IS Net Income

**Answer:** **5 brokers**, with a median of **402,000**. The forecasts range from 368,000 to 488,000.

### Example 5: Al Rajhi Bank's expected profit

> **"How much is Al Rajhi Bank expected to earn in 2026?"**

**Enter:** TASI, `1120`, Annual
**Find:** `forYear` = 2026 and `fsFieldNameEn` = IS Net Income

**Answer:** **8 brokers**, with a median of **27,795.5**. The forecasts range from 26,785 to 30,210.

### Example 6: Saudi Telecom's expected sales

> **"What sales do analysts expect from STC in 2026?"**

**Enter:** TASI, `7010`, Annual
**Find:** `forYear` = 2026 and `fsFieldNameEn` = Sales

**Answer:** **9 brokers**, with a median of **81,204**. The forecasts range from 78,451 to 84,876.

### Example 7: Is Almarai's profit expected to grow?

> **"Do analysts expect Almarai's profit to rise between 2026 and 2029?"**

**Enter:** TASI, `2280`, Annual
**Find:** `fsFieldNameEn` = IS Net Income, for `forYear` 2026 and 2029

**Answer:** yes. The median goes from **2,558** in 2026 (13 brokers) to **3,303** in 2029 (4 brokers).

### Example 8: Do analysts agree on Jarir?

> **"How close together are the 2026 profit forecasts for Jarir?"**

**Enter:** TASI, `4190`, Annual
**Find:** `forYear` = 2026 and `fsFieldNameEn` = IS Net Income

**Answer:** very close. **5 brokers** range only from **1,080 to 1,140**, with a median of 1,111.2.

### Example 9: A quarterly forecast for SABIC

> **"What do analysts expect SABIC to earn in the third quarter of 2026?"**

**Enter:** TASI, `2010`, Quarterly
**Find:** `forYear` = 2026, `fiscalPeriodValue` = Q3 and `fsFieldNameEn` = IS Net Income

**Answer:** **11 brokers**, with a median of **342**. They disagree a lot: the forecasts range from -673 to 2,264, and a minus sign means a loss.

---

## NOMU examples

NOMU companies usually have one broker per forecast, so there is no median or range to compare. The NOMU data is annual only.

### Example 10: Alhasoob's 2025 forecast

> **"What sales and profit were forecast for Alhasoob in 2025?"**

**Enter:** NOMU, `9522`, Annual
**Find:** `forYear` = 2025, with `fsFieldNameEn` = Sales and IS Net Income

**Answer:** sales of **303.1** and net income of **12.6**.

### Example 11: Basma Adeem Medical's long-term forecast

> **"How much is Basma Adeem Medical's profit forecast to grow by 2029?"**

**Enter:** NOMU, `9626`, Annual
**Find:** `fsFieldNameEn` = IS Net Income, for `forYear` 2025 and 2029

**Answer:** from **9.7** in 2025 to **21.5** in 2029.

### Example 12: Tam Development in 2026

> **"What are the 2026 forecasts for Tam Development?"**

**Enter:** NOMU, `9570`, Annual
**Find:** `forYear` = 2026

**Answer:** sales of **358** and net income of **75**.

### Example 13: Mufeed's profit by year

> **"What profit is forecast for Mufeed each year?"**

**Enter:** NOMU, `9615`, Annual
**Find:** all 3 rows, which are all IS Net Income

**Answer:** **35.626** in 2025, **37.23** in 2026 and **39.091** in 2027.

---

## Investment funds examples

Open the **Investment funds** tab, choose what to **Show**, then a **Fund manager** and a **Fund**. The examples below are already saved, so they use no API calls. You can also open the files under `data/funds/` directly.

### Example 14: Who manages funds in Saudi Arabia?

> **"Which firms run investment funds?"**

**Open:** `data/funds/fund_managers.json`
**Answer:** 46 managers, e.g. Al Rajhi Capital (`2604`), Riyad Capital (`2501`), SNB Capital (`2930`) and Jadwa Investment (`3772`).

### Example 15: How many funds does Al Rajhi Capital run?

> **"What funds can I buy from Al Rajhi Capital?"**

**Open:** `data/funds/manager_funds/2604.json` (from `/funds/managers/2604/funds`)
**Answer:** **40** funds, e.g. AL RAJHI SAVING AND LIQUIDITY FUND - USD (`2`) and AL RAJHI ARAB EQUITY MARKETS FUND (`15`).

### Example 16: What does a fund cost?

> **"What are the fees on the Riyad Emaar Fund?"**

**Open:** `data/funds/fund_details/2501_260.json` (from `/funds/managers/2501/funds/260`)
**Find:** `managementFeePercent`, `managementFeeTypeEn`, `subscriptionFeePercent`, `custodianFeePercent`
**Answer:** **1.75%** a year to manage, **1%** to subscribe and **0.035%** a year for the custodian (plus $10 a transaction). The fund started on 30 December 2009 at 10 riyals a unit and holds about **63 million riyals**.

### Example 17: How has a fund performed?

> **"Has the Riyad Emaar Fund made money?"**

**Show:** Price history · **Manager:** Riyad Capital · **Fund:** Riyad Emaar Fund
(file `data/funds/fund_history/2501_260.json`)
**Answer:** the unit price was **20.35** on 5 Nov 2026, down **10.2%** this year and **18.1%** over 12 months. It has still roughly doubled (**+103%**) since its first price in 2009. Hover over the chart for any day's price.

### Example 18: A steady savings fund

> **"How has Al Rajhi's US dollar savings fund grown since 1990?"**

**Show:** Price history · **Manager:** Al Rajhi Capital Company · **Fund:** AL RAJHI SAVING AND LIQUIDITY FUND - USD
(file `data/funds/fund_history/2604_2.json`)
**Answer:** from **1,000** a unit in December 1990 to **2,827.70** on 5 Nov 2026 (**+183%**), and **+3.4%** so far this year. The chart is a slow, steady climb, as expected for a liquidity fund.

### Example 19: A Shariah money market fund

> **"How has the ANB Capital SAR Trade Fund done over the years?"**

**Show:** Price history · **Manager:** ANB Capital (`2725`) · **Fund:** ANB Capital SAR Trade Fund (Shariah) (`77`)
(file `data/funds/fund_history/2725_77.json`)
**Answer:** from **10** riyals a unit in January 1993 to **27.43** on 5 Nov 2026 (**+174%**), **+4.2%** so far this year and **+5.0%** over 12 months. The fund holds about **3.4 billion riyals**. The chart barely dips: yearly returns sat near 1% in 2010 to 2015 and rose to about 5.5% a year in 2023 to 2025 as interest rates went up.

### Example 20: Which funds moved most this year?

> **"Which funds are up and down the most this year?"**

**Show:** Top-moving funds this year (file `data/funds/fund_movers.json`)
**Answer:** the top gainer is **SNB Capital Emerging Markets Index Fund, +25.8%**, and the top loser is **AlAhli SEDCO Residential Development Fund, -67.0%**. The table lists the 10 of each.

### Example 21: What is a fund worth today?

> **"What is one unit of the Riyad Emaar Fund worth right now?"**

**Show:** Latest value · **Manager:** Riyad Capital · **Fund:** Riyad Emaar Fund
(file `data/funds/fund_values/2501_260.json`, from `/funds/managers/2501/funds/260/values`)
**Answer:** **20.35** riyals a unit on 5 Nov 2026, **-10.2%** this year, with about **23.9 million riyals** in the fund. This is the same as the newest row of its price history, in one small file.

---

## M&A & Transactions examples

Open the **M&A & Transactions** tab, choose a **Market** and click **Show deals**. The filters (type, status, year, company) update the tiles, chart and table straight away. To see one deal's full record, pick it in **One deal's full record**. The examples below are already saved, so they use no API calls. You can also open the files under `data/m&a/` directly.

### Example 22: How busy is the Saudi M&A market?

> **"How many deals do TASI companies make, and how many go through?"**

**Market:** TASI (3) · **Show deals** (file `data/m&a/market_deals/3.json`)
**Answer:** **615** deals from 2004 to 2026. **68%** completed and **17%** were cancelled. The chart shows the busiest years: **2023 (57)**, 2022 (55) and 2025 (53). In 2026 so far, 10 of the 30 deals are still in negotiation.

### Example 23: Saudi Aramco's deals

> **"What has Aramco bought, and what was the biggest deal?"**

**Market:** TASI · **Company:** `aramco`
**Answer:** **23** deals (19 completed). The "Largest deal" tile shows Aramco buying **a stake in SABIC for $69,000 million** (deal `17`, 2018, financed by loans). The table lists the others, newest first, e.g. Sahel (2026) and HUMAIN (2025, with PIF as related company).

### Example 24: How was a deal paid for?

> **"How did Aramco pay for its Petro Rabigh deal?"**

**Company:** `aramco` · **One deal's full record:** `2024-08-07 · SAUDI ARAMCO → PETRO RABIGH (600)`
(file `data/m&a/deal_details/600.json`)
**Answer:** an "Acquisition of majority Assets", **completed**, worth **702 million USD**, financed by **Internal Resources**. Sumitomo Chemical is listed as the related company.

### Example 25: Mergers that fell apart

> **"How often are mergers cancelled?"**

**Market:** TASI · **Deal type:** Merger · **Status:** Cancelled
**Answer:** **18** of the 43 mergers were cancelled. One of them is UCA and AICC (deal `648`, June 2025). Pick it in **One deal's full record**: it was to be paid by **Share Swap**, and no value was disclosed.

### Example 26: Deals on NOMU

> **"Do the smaller NOMU companies do deals too?"**

**Market:** NOMU (14) · **Show deals** (file `data/m&a/market_deals/14.json`)
**Answer:** **19** deals since 2020, 10 completed. Pick `ALRASHEED → Taif Shipping (715)`: an acquisition worth **24.6 million USD**, agreed ("Certain"), paid from internal resources and loans.

---

## Projects & Capital Investments examples

Open the **Projects & Capital Investments** tab, choose a **Market** and click **Show projects**. The filters (status, country, year) update the tiles, chart and table straight away. Pick a project in **One project's full record**, or a company in **A company: its projects and key developments**. The examples below are already saved, so they use no API calls. You can also open the files under `data/projects/` directly. Costs are in millions of riyals.

### Example 27: How big is the TASI project pipeline?

> **"How many projects do TASI companies have, and what are they worth?"**

**Market:** TASI (3) · **Show projects** (file `data/projects/projects_by_market/3.json`)
**Answer:** **1,696** projects announced from 1959 to 2026. **742** have a disclosed cost, **SAR 4,640bn** in all (about $1,237bn). The largest is **NEOM, SAR 1,875bn**. **291** are under construction and **1,115** (66%) completed. The chart shows the busiest year was **2022 (204 projects)**.

### Example 28: What are NOMU companies building?

> **"Which smaller companies are building something right now?"**

**Market:** NOMU (14) · **Status:** Under Construction
**Answer:** **51** projects, 30 of them with a cost, **SAR 3.8bn** together. The "Largest project" tile shows **Industrial land (Al Kharj), SAR 700m**, followed by Faran Mountain (SAR 602m) in the table.

### Example 29: One project in full

> **"What is ACWA building with its Bash 2 project, and when will it be done?"**

**Market:** TASI · **Status:** Under Construction · **One project's full record:** `2026 · Bash 2 Independent Wind Power Plant (2269)`
(file `data/projects/project_details/2269.json`)
**Answer:** a **300 MW** wind power plant in **Uzbekistan**, owned by ACWA, category Power and Water, starting in 2026 and expected in **2027**. The Updates row says that in May 2026 ACWA signed **$226 million** of financing with the Asian Development Bank, AIIB and Standard Chartered. No cost is disclosed.

### Example 30: Projects that were cancelled

> **"How often are TASI projects cancelled, and how much money was involved?"**

**Market:** TASI · **Status:** Cancelled
**Answer:** **51** projects, 31 with a cost, **SAR 157bn** together, the largest the **COTC Complex (SAR 112.5bn, 2014)**. Pick `2025 · Specialty Chemicals Plant (1892)`: a joint venture of BCI and South Africa's AECI to make specialty chemicals in the Kingdom, agreed in May 2025 and since cancelled.

### Example 31: A company's projects next to its history

> **"What is ACWA doing, and what has happened at the company?"**

**A company:** `ACWA POWER Co. (2082)`
(files `data/projects/_company_projects.json` and `data/projects/company_developments/2082.json`)
**Answer:** **116** projects, more than any other company: **32** as owner and the rest as a related company (often as developer or partner), **24** under construction, and **SAR 480bn** of disclosed cost across 102 of them. The chart shows the busiest year was **2025 (17 projects)**. The table puts the projects and the **15** key developments in one list, newest first, e.g. the Bash 2 wind plant (May 2026), the **rebrand from "ACWA Power" to "Acwa" (January 2026)** and a **rights issue that raised capital to SAR 7,665m (July 2025)**, back to its founding in 2008.

### Example 32: Aramco's milestones

> **"What are the big moments in Saudi Aramco's history?"**

**A company:** `Saudi Arabian Oil Co. (2222)` (file `data/projects/company_developments/2222.json`)
**Answer:** **39** key developments from **1933**, when Saudi Arabia signed the oil concession with Standard Oil of California, to **26 February 2026**, when production started at **Jafurah**, the Middle East's largest unconventional gas field. Each row links to the Argaam article. The same view lists **85** projects that name Aramco (49 as owner), such as Luberef's Group III+ base oil plant (`2179`), where Aramco is the related company.

---

## Good to know

- **Not every company has estimates.** 212 companies do. For the rest, including any NOMU company with the Quarterly period, the app shows a no-data message. That is expected and is not a bug.
- **The sandbox is mostly empty in step 3.** Fields with numbers: `33/125`, `33/128` and `51/103`, `51/104`, `51/105`. Others, such as fuel prices (`143/760`), unemployment (`130/484`), oil production (`35`), listed companies (`178`) and tourists (`102`), return HTTP 204 (no data). Steps 1 and 2 work for every group.
- **HTTP 429** means you called too fast. Wait a few seconds and retry.
- **Investment funds are all saved:** 46 managers and 499 funds, 358 of them with price history. The other 141 returned no prices (HTTP 204), often because they have closed.
- **M&A deals are all saved:** both market lists and all 634 deal records.
- **M&A values are in two currencies** (million USD or million riyals), and deal `477` has a value that is off by a million. The tab compares in USD (3.75 riyals a dollar) and leaves that deal out of "Largest deal".
- **Project costs are in millions of riyals,** although the API doesn't say so (NEOM's 1,875,000 is $500 billion). The market lists repeat some projects in identical rows; the tab counts each project once.
- **Projects are all saved:** both market lists, all 1,966 project records and the key developments of 416 of the 417 listed companies (`9551` has none).
- For a description of every field, see [EXPLAINED.md](EXPLAINED.md).
