# Explained: what each endpoint returns

This file describes the data each Argaam API endpoint in this project returns. For every endpoint you get what it gives you, what each field means, and a real example.

The examples are real responses from the sandbox (`https://api-sandbox.argaam.com/api/v1.1`), shortened to keep them readable.

---

## The big picture: three levels

The indicator endpoints work like a folder tree. Each level gives you the IDs you need for the next one:

```
/indicators/groups                               -> "Which topics exist?"           (gives groupID)
  └─ /indicators/groups/{groupId}/fields         -> "Which numbers does a topic have?" (gives fieldID)
       └─ /indicators/groups/{groupId}/fields/{fieldId}/values -> "What are the actual numbers?"
```

A real path through the tree:

| Step | Call | Result |
|------|------|--------|
| 1 | `/indicators/groups` | Group **17 "Macro"** has a sub-group **33 "National Accounts"** |
| 2 | `/indicators/groups/33/fields` | Group 33 has field **125 "Gross Domestic Product at Current Prices (Base year 2010)"** |
| 3 | `/indicators/groups/33/fields/125/values` | GDP for **2026 = 4431** |

---

## 1. Indicator groups

**Path:** `GET /indicators/groups`
**Parameters:** none
**Saved as:** `data/indicator_groups.json`

### What data it returns
This is the catalogue of every macroeconomic topic Argaam covers. It contains no numbers, only names and IDs. You use it to find the `groupID` you need.

It returns a **list of 29 main groups** (Macro, Unemployment, Oil & Gas, Tourism, Housing, ...). Each main group has a list of **sub-groups**, which are the specific tables.

### Fields

| Field | Type | Meaning |
|-------|------|---------|
| `groupID` | number | ID of the main group |
| `nameEn` / `nameAr` | text | Group name in English / Arabic |
| `subGroups` | list | The specific tables inside this group |
| `subGroups[].groupID` | number | ID of the sub-group. **This is the `{groupId}` used in the next endpoint** |
| `subGroups[].parentGroupID` | number | Which main group it belongs to (equals the parent's `groupID`) |
| `subGroups[].nameEn` / `nameAr` | text | Sub-group name |

### Example
```json
[
  {
    "groupID": 17,
    "nameAr": "مؤشرات الاقتصاد الكلي",
    "nameEn": "Macro",
    "subGroups": [
      { "groupID": 33,  "parentGroupID": 17, "nameEn": "National Accounts" },
      { "groupID": 277, "parentGroupID": 17, "nameEn": "GDP Growth Rates (%)" },
      { "groupID": 365, "parentGroupID": 17, "nameEn": "Population according to administrative regions" }
    ]
  },
  { "groupID": 197, "nameEn": "Unemployment", "subGroups": [ ... 25 sub-groups ... ] },
  { "groupID": 21,  "nameEn": "Oil & Gas",    "subGroups": [ ... 8 sub-groups ... ] }
]
```

### In practice
> "I want Saudi GDP data. Where do I look?"
> Open the list, find **Macro (17)**, look in its sub-groups and find **National Accounts (33)**. You now have `groupId = 33`.

All 29 main groups (with how many sub-groups each has): Macro (22), Building & Construction (4), Govt Budget (5), Unemployment (25), Money Statistics (28), Stock Market (12), Financing Companies (5), Saudi foreign aid (1), Oil & Gas (8), Fuel prices (2), Telecom (4), Travel and Aviation (5), Tourism (10), Hajj and Umrah (2), Automobiles (1), Industrialization (13), Mining (4), Steel Prices (3), Electricity (6), Water (8), Healthcare (13), Insurance (20), Education (6), Agriculture (5), Housing (11), Properties (14), Municipal and rural affairs (6), Mutual Funds (3), Traffic and Transport Statics (55).

---

## 2. Indicator group fields

**Path:** `GET /indicators/groups/{groupId}/fields`
**Parameters:** `groupId` is a sub-group ID from endpoint 1 (e.g. `33`)
**Saved as:** `data/indicators_groups_<id>_fields.json` (named after the path)

### What data it returns
The list of **indicators (measurements)** inside one group, such as "Population", "GDP per capita" or "Debt to GDP". Like endpoint 1, it has no numbers yet, only the names and IDs. You use it to find the `fieldID`.

### Fields

| Field | Type | Meaning |
|-------|------|---------|
| `fieldID` | number | ID of the indicator. **This is the `{fieldId}` used in the next endpoint** |
| `displayNameEn` / `displayNameAr` | text | Indicator name in English / Arabic |

### Example: `/indicators/groups/33/fields` (National Accounts)
```json
[
  { "fieldID": 58,  "displayNameEn": "Population" },
  { "fieldID": 59,  "displayNameEn": "GDP per capita" },
  { "fieldID": 125, "displayNameEn": "Gross Domestic Product at Current Prices (Base year 2010)" },
  { "fieldID": 126, "displayNameEn": "Gross Domestic Product at Chain-Linked Methodology (Base year 2010)" },
  { "fieldID": 127, "displayNameEn": "GDP Growth at Current Prices" },
  { "fieldID": 128, "displayNameEn": "GDP Growth at Chain-Linked Methodology" },
  { "fieldID": 170, "displayNameEn": "Debt to GDP" }
]
```

Another example, `/indicators/groups/277/fields` (GDP Growth Rates %), breaks growth down by sector: `3584` Agriculture, forestry & fishing · `3586` Mining & quarrying · `3589` Manufacturing · `3594` Construction · `3604` Government activities · ...

### In practice
> "Within National Accounts, which one is nominal GDP?"
> It is field **125**, "GDP at Current Prices". You now have `groupId = 33`, `fieldId = 125`.

---

## 3. Indicator series (values)

**Path:** `GET /indicators/groups/{groupId}/fields/{fieldId}/values`
**Parameters:** `groupId` from endpoint 1 and `fieldId` from endpoint 2
**Saved as:** `data/indicators_groups_<g>_fields_<f>_values.json`

### What data it returns
**The actual numbers.** It returns a time series for one indicator, meaning one value per year and period.

### Fields

| Field | Type | Meaning |
|-------|------|---------|
| `economicIndicatorFieldID` | number | The field you asked for (same as `fieldId`) |
| `displayNameEn` / `displayNameAr` | text | Indicator name |
| `values` | list | The time series, one entry per period |
| `values[].year` | number | Year of the data point |
| `values[].fiscalPeriodTypeID` | number | What kind of period it is (e.g. annual, quarterly, monthly). See note below |
| `values[].fiscalPeriodID` | number | Which period within the year (e.g. quarter 1). See note below |
| `values[].value` | number | **The number itself** |

### Example: `/indicators/groups/33/fields/125/values`
```json
{
  "economicIndicatorFieldID": 125,
  "displayNameEn": "Gross Domestic Product at Current Prices (Base year 2010)",
  "values": [
    { "year": 2026, "fiscalPeriodTypeID": 4, "fiscalPeriodID": 1, "value": 4431 }
  ]
}
```

### In practice
> "What is Saudi GDP at current prices?"
> **4431** for 2026. Each item in `values` becomes one row in a table or database: `field=125, year=2026, period=1, value=4431`.

### Notes
- **Units are not in the response.** For GDP the number is most likely in billions of SAR, but the API does not say so. Check Argaam's documentation before using the numbers in reports.
- **`fiscalPeriodTypeID` / `fiscalPeriodID` are codes** and the API does not explain them. Confirm their meaning with Argaam's documentation or a lookup endpoint before relying on them.
- **The sandbox has gaps.** Many fields return **HTTP 204 (no data)**. For example, `33/58` (Population) and `33/59` (GDP per capita) were empty when tested. The viewer shows this as "No data returned". It is not a bug in this project.
- **Rate limit.** If you call the sandbox too fast it returns **HTTP 429 Too Many Requests**. Wait a little and try again.

---

## Adding a new endpoint to this file
When you add an endpoint to `ENDPOINTS` in `app.py`, add a section here with the same parts:

1. **Path and parameters**: where the IDs come from
2. **What data it returns**: one or two plain sentences
3. **Fields table**: every field and what it means
4. **Example**: a real, shortened response
5. **In practice**: a question and how this endpoint answers it
