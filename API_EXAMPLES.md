# API Examples

One real example that uses all three endpoints, step by step. Every response below is a real response from the sandbox.

## The question

> **"How big is Saudi Arabia's economy?"**

An analyst wants Saudi GDP, the total value of everything the country produces in a year. They don't know the IDs yet, so they find them one step at a time:

```
1. Which topics exist?               → "National Accounts" → groupId = 33
2. What is inside National Accounts? → "GDP"               → fieldId = 125
3. Give me the number                → 2026 = 4431
```

## How to try it

Run `python app.py`, open http://127.0.0.1:5001, paste each path below into the **Path** box and click **Fetch**.

---

## Step 1: Find the topic

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

## Step 2: Find the indicator

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

## Step 3: Get the number

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

## Good to know

- **The sandbox is mostly empty in step 3.** `33/125` is the only field we found that returns numbers. Others, such as fuel prices (`143/760`) and unemployment (`130/484`), return HTTP 204 (no data). Steps 1 and 2 work for every group.
- **HTTP 429** means you called too fast. Wait a few seconds and retry.
- For a description of every field, see [EXPLAINED.md](EXPLAINED.md).
