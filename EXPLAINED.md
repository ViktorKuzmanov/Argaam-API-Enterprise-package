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

`fetch_macroeconomic.py` walks this whole tree for you: every group, then every group's fields, then every field's values. It saves each response under `data/macroeconomic/` (see the README for how to run it).

---

## 1. Indicator groups

**Path:** `GET /indicators/groups`
**Parameters:** none
**Saved as:** `data/macroeconomic/indicator_groups.json`

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
**Saved as:** `data/macroeconomic/indicator_fields/<groupId>.json`, e.g. `indicator_fields/33.json`

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
**Saved as:** `data/macroeconomic/indicator_values/<groupId>_<fieldId>.json`, e.g. `indicator_values/33_125.json`

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

## Fundamentals: analyst estimates

**Path:** `GET /companies/{stockSymbol}/analyst-estimates?marketId=3&period=year`
**Parameters:**

| Parameter | Required | Values |
|-----------|----------|--------|
| `stockSymbol` | yes | Tadawul symbol, e.g. `2222` (Saudi Aramco), `1120` (Al Rajhi Bank) |
| `marketId` | yes | `3` = TASI, `14` = NOMU. Without it the API answers "This Market is not Supported". Dubai, Abu Dhabi, Kuwait, Qatar, Muscat and Bahrain were all rejected in the sandbox |
| `period` | no | `year` (default) or `quarter` |

**Saved as:** `data/fundamentals/analyst_estimates/<marketId>_<symbol>_<period>.json`, e.g. `analyst_estimates/3_2222_year.json`

### What data it returns
Broker forecasts of a company's financial statement lines. There is **one row per broker, per metric, per period**, so you combine rows yourself to get a consensus.

The metrics differ by company. Aramco has Net Income, Sales and Total Income. Al Rajhi Bank has Net Income, Operating Income, Operating Profit, Total Assets, Customer Deposits and Net Financing Investments.

### Fields

| Field | Type | Meaning |
|-------|------|---------|
| `analystEstimatesFinancialStatementValueID` | number | ID of this one estimate (unique per row) |
| `analystEstimatesFinancialStatementID` | number | ID of the broker's submission; one submission can cover several metrics |
| `fsFieldCategoryID` | number | Statement section: `1` for income statement lines, `2` for balance sheet lines (inferred from the metrics) |
| `fsFieldID` | number | Metric ID, e.g. `54` = Net Income |
| `fsFieldNameEn` / `fsFieldNameAr` | text | Metric name in English / Arabic |
| `marketID` | number | Market, e.g. `3` = TASI |
| `companyID` | number | Argaam's company ID (not the stock symbol: Aramco is `3509`) |
| `companyNameEn` / `companyNameAr` | text | Company name |
| `forYear` | number | Year being forecast |
| `fiscalPeriodValue` | text | `YEAR`, `Q1`, `Q2`, `Q3` or `Q4` |
| `fiscalPeriodID` | text | Numeric period code: `1` = year, `2`-`5` = Q1-Q4 |
| `forDate` | date | Last day of the period being forecast |
| `value` | number or null | The forecast. Can be null |
| `brokerID` | number | Broker ID. The response has no broker names |

### Example
`/companies/2222/analyst-estimates?marketId=3&period=year` (shortened)

```json
{
  "data": {
    "companyId": 3509,
    "marketId": 3,
    "period": "year",
    "estimates": [
      {
        "fsFieldID": 54,
        "fsFieldNameEn": "IS Net Income",
        "companyNameEn": "Saudi Arabian Oil Co.",
        "forYear": 2029,
        "fiscalPeriodValue": "YEAR",
        "forDate": "2029-12-31T00:00:00",
        "value": 560966.0,
        "brokerID": 3939
      }
    ]
  }
}
```

### What to watch for
- **Not in the response:** broker names, the date an estimate was made, currency or units, actual results, target prices and recommendations.
- **Units:** not stated, but Saudi companies' values line up with millions of SAR.
- **Revisions:** a broker can have several rows for the same metric and period. With no estimate date, the highest `analystEstimatesFinancialStatementValueID` is the best guess at the newest.
- **Past periods stay in the data.** Al Rajhi goes back to 2014. These are old forecasts, not reported results.
- **Thin coverage:** far-out years can have one or two brokers, and some metrics disagree wildly (one Al Rajhi metric ranges from 12,550 to 240,000 for 2018), possibly because brokers define it differently. Prefer the median and check the broker count.
- **Rate limit:** 5 requests a minute and 100 a day for this endpoint in the sandbox.

### In practice
"What do analysts expect Aramco to earn in 2026?" Fetch symbol `2222` on TASI, annual, and look at the rows where `forYear` is 2026 and `fsFieldNameEn` is `IS Net Income`: 5 brokers, median 402,000, ranging from 368,000 to 488,000.

---

## Investment funds: managers, funds, details, price history, movers

Like the indicators, each level gives you the IDs for the next one. The real numbers are in the price history:

```
/funds/managers                                      -> "Which fund managers exist?"       (gives fundManagerID)
  └─ /funds/managers/{managerId}/funds               -> "Which funds does a manager run?"  (gives fundID)
       ├─ /funds/managers/{managerId}/funds/{fundId}  -> "What is this fund, what does it cost?"
       └─ .../funds/{fundId}/values/history?from=&to= -> "What was it worth each day?"
/funds/movers                                        -> "Which funds moved most this year?"
```

**Saved as:** `data/funds/fund_managers.json`, `manager_funds/<managerId>.json`, `fund_details/<managerId>_<fundId>.json`, `fund_history/<managerId>_<fundId>.json` and `fund_movers.json`, all under `data/funds/`. `fetch_funds.py` fetches them in that order, and the **Investment funds** tab shows them.

### 1. Fund managers: `GET /funds/managers`
A list of the 46 fund-management firms Argaam tracks.

| Field | Type | Meaning |
|-------|------|---------|
| `fundManagerID` | number | Manager ID, used in the next two paths |
| `companyNameEn` / `companyNameAr` | text | Firm name in English / Arabic. Some have a trailing space |

The Argaam docs also promise the licensing jurisdiction and a fund count, but the sandbox does not return them.

### 2. Funds of a manager: `GET /funds/managers/{managerId}/funds`
A list of that manager's funds: Al Rajhi Capital (`2604`) has 40, Riyad Capital (`2501`) has 41.

| Field | Type | Meaning |
|-------|------|---------|
| `fundID` | number | Fund ID, used with the manager ID in the next path |
| `fundNameEn` / `fundNameAr` | text | Fund name |

### 3. Fund details: `GET /funds/managers/{managerId}/funds/{fundId}`
One object describing the fund.

| Field | Type | Meaning |
|-------|------|---------|
| `fundID`, `fundNameEn` / `fundNameAr` | | The fund |
| `fundManagerID`, `fundManagerNameEn` / `fundManagerNameAr` | | Its manager |
| `fundObjectiveEn` / `Ar` | text | What the fund aims for, in one or two sentences |
| `investmentStrategyEn` / `Ar` | HTML | How it invests. Contains HTML tags and `&nbsp;`, so strip them before showing it as text |
| `valuationNotesEn` / `Ar` | text | How the fund is valued |
| `eligibilityEn` / `Ar` | text | Who can invest |
| `inceptionDate` | date | When the fund started |
| `inceptionPrice` | number | Unit price at the start |
| `fundSize` | number or null | Size of the fund, in its currency |
| `currencyNameEn` / `Ar` | text | e.g. `Riyal`, `USD` |
| `minSubscriptionFee` | number | Despite the name, looks like the minimum first investment (`100` for a fund with a 5,000 minimum is unlikely to be a fee) |
| `minRedemption` | number | Minimum amount you can take out |
| `subscriptionChargeAmount` | number | Probably the minimum subscription amount |
| `managementFeePercent`, `managementFeeTypeEn` / `Ar` | number, text | Management fee and how often, e.g. `1.75`, `Per annum` |
| `performanceFeePercent`, `subscriptionFeePercent`, `custodianFeePercent` | number | Other fees, in percent |
| `custodianFeeAdditionalInformationEn` / `Ar` | text or null | Extra detail on the custodian fee |

### Example
`/funds/managers/2501/funds/260` (shortened)

```json
{
  "fundID": 260,
  "fundNameEn": "Riyad Emaar Fund",
  "fundManagerNameEn": "Riyad Capital ",
  "fundObjectiveEn": "The fund aims to achieve long term capital growth through investing primarily in stocks of listed Saudi companies engaged in building, construction, real estate and cement.",
  "inceptionDate": "2009-12-30T00:00:00",
  "inceptionPrice": 10.0,
  "fundSize": 62961821.0,
  "currencyNameEn": "Riyal",
  "managementFeePercent": 1.75,
  "managementFeeTypeEn": "Per annum",
  "subscriptionFeePercent": 1.0
}
```

### What to watch for
- **Less than the docs promise.** Argaam's docs say fund details include the benchmark, distribution policy, latest NAV and reference dates. The sandbox returns none of them. Prices come from the price history (section 4).
- **Odd values.** Al Rajhi's US dollar savings fund (`2604/2`) shows a management fee of `16.0` percent with no fee type, which is not believable for a liquidity fund. Check fees before relying on them.
- **Missing values.** `fundSize` and the fee type can be null.

### In practice
"What does the Riyad Emaar Fund invest in, and what does it cost?" Fetch `/funds/managers/2501/funds/260`: Saudi building, real estate and cement shares, a 1.75% yearly management fee and a 1% subscription fee.

### 4. Price history: `GET /funds/managers/{managerId}/funds/{fundId}/values/history?from=yyyy-MM-dd&to=yyyy-MM-dd`
Every end-of-day price of the fund between the two dates. **Without `from` and `to` it returns HTTP 204 (no data)**, so `fetch_funds.py` and the app always ask from `1980-01-01` to today, which gives the whole history in one call. The file name has no dates, so a later `--refresh` replaces it with a longer history.

| Field | Type | Meaning |
|-------|------|---------|
| `fundManagerID`, `fundID`, `fundNameEn` / `fundNameAr` | | The fund |
| `values[].valueDate` | date | The day of the price |
| `values[].unitPrice` | number | Price of one unit that day, in the fund's currency. This is what an investor's return follows |
| `values[].netAssetValue` | number | Total value of the fund that day (NAV), in its currency. It moves with money coming in and out, not only with performance |
| `values[].ytd` | number | Return since the start of that year, in percent |

```json
{
  "fundID": 2,
  "fundNameEn": "AL RAJHI SAVING AND LIQUIDITY FUND - USD",
  "values": [
    {"valueDate": "2026-11-05T00:00:00", "ytd": 3.3904, "unitPrice": 2827.6998, "netAssetValue": 85359730.77},
    {"valueDate": "1990-12-01T00:00:00", "ytd": 0, "unitPrice": 1000.0, "netAssetValue": 448044318.0}
  ]
}
```

- **Not in date order.** Sort `values` by `valueDate` yourself (the app does).
- **Daily or weekly.** Most funds have a price every working day; older years can be weekly or sparse (Al Rajhi's USD fund has almost nothing between 1991 and 2001).
- **Some funds have none.** 31 of the first 145 funds returned HTTP 204, often funds that have closed. They are recorded as `no_data`.
- **Size:** a typical fund has about 1,750 prices (up to about 3,100), roughly 150 KB of JSON.
- In practice: "How has the Riyad Emaar Fund done?" Its unit price was **20.35** on 5 Nov 2026: **-10.2%** this year, **-18.1%** over 12 months, and **+103%** since its first price in 2009.

### 5. Top-moving funds: `GET /funds/movers`
Two lists of 10: `gainers` and `losers`, ranked by this year's return. Each row has `fundID`, `fundNameEn` / `Ar`, `assetTypeNameEn` (e.g. `Growth`, `Income & Growth`), `currencyNameEn`, `valueDate`, `unitPrice`, `ytd` (percent) and `nav`.

- `fundManagerID` is always `0` here, so to open the fund elsewhere, find its `fundID` in the managers' fund lists.
- `netAssetValue` is null; use `nav` instead. `totalRecords` (356) looks like the number of funds that were ranked.
- Each fund's `valueDate` is its own latest price, which can be months old (the biggest loser's is 30 June 2026).
- In practice: on 5 Nov 2026 the biggest gainer was **SNB Capital Emerging Markets Index Fund, +25.8%** this year. The biggest loser was **AlAhli SEDCO Residential Development Fund, -67.0%** (as of 30 June).

---

## Adding a new endpoint to this file
When you add an endpoint to `ENDPOINTS` in `app.py`, add a section here with the same parts:

1. **Path and parameters**: where the IDs come from
2. **What data it returns**: one or two plain sentences
3. **Fields table**: every field and what it means
4. **Example**: a real, shortened response
5. **In practice**: a question and how this endpoint answers it
