# API Examples

Real examples you can try in the app. Examples 1 to 3 use the three indicator endpoints, step by step. Examples 4 to 13 use analyst estimates from both markets. Every response below is a real response from the sandbox.

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

## Good to know

- **Not every company has estimates.** 212 companies do. For the rest, including any NOMU company with the Quarterly period, the app shows a no-data message. That is expected and is not a bug.
- **The sandbox is mostly empty in step 3.** Fields with numbers: `33/125`, `33/128` and `51/103`, `51/104`, `51/105`. Others, such as fuel prices (`143/760`), unemployment (`130/484`), oil production (`35`), listed companies (`178`) and tourists (`102`), return HTTP 204 (no data). Steps 1 and 2 work for every group.
- **HTTP 429** means you called too fast. Wait a few seconds and retry.
- For a description of every field, see [EXPLAINED.md](EXPLAINED.md).
