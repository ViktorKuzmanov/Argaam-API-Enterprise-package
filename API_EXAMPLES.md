# API Examples

Three real examples that each use all three endpoints, step by step. Every response below is a real response from the sandbox.

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

## Good to know

- **The sandbox is mostly empty in step 3.** Fields with numbers: `33/125`, `33/128` and `51/103`, `51/104`, `51/105`. Others, such as fuel prices (`143/760`), unemployment (`130/484`), oil production (`35`), listed companies (`178`) and tourists (`102`), return HTTP 204 (no data). Steps 1 and 2 work for every group.
- **HTTP 429** means you called too fast. Wait a few seconds and retry.
- For a description of every field, see [EXPLAINED.md](EXPLAINED.md).
