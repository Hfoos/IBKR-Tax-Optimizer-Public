# Israeli Tax Rules: Shares Traded via a Foreign Broker

> **Disclaimer:** This document is for informational purposes only and does not constitute legal or tax advice. Consult a licensed Israeli tax advisor (רואה חשבון / יועץ מס) for your specific situation. Tax rules are subject to change.

---

## 1. Who This Applies To

Israeli tax residents who hold and trade shares through a foreign brokerage account (e.g., Interactive Brokers, Schwab, TD Ameritrade). Unlike Israeli brokers, foreign brokers do **not** withhold tax on behalf of the Israeli Tax Authority (רשות המסים). The taxpayer is fully responsible for self-reporting and payment.

---

## 2. Capital Gains Tax Rate

| Shareholder Type | Tax Rate |
|---|---|
| Regular individual (less than 10% ownership in the company) | **25%** |
| Substantial shareholder (10% or more ownership in the company) | **30%** |

- The 10% threshold ("בעל מניות מהותי") applies per company, and considers indirect holdings as well.
- There is **no reduced rate for long-term holdings** — the flat rate applies regardless of how long shares were held.

---

## 3. Calculating the Taxable Gain

### 3.1 All Calculations Are in NIS

Even if transactions are conducted in USD (or any other currency), the capital gain must be calculated in **Israeli Shekels (NIS)** using the **Bank of Israel representative exchange rate** (שער יציג) on each relevant date.

**Allowable Expenses** (brokerage commissions, direct transaction costs) are subtracted from proceeds, converted to NIS at the rate on the transaction date.

### 3.2 The Three-Step Formula

Because the purchase and sale occur at different USD/NIS rates, Israeli tax law requires two parallel calculations to determine the taxable result (רווח ריאלי). The outcome depends on the signs of both results.

**Step 1 — Convert sale proceeds to NIS**
```
Proceeds (NIS) = Shares × Sale price (USD) × USD/NIS rate on sale date
```

**Step 2 — Convert purchase cost to NIS twice**
```
Cost A = Shares × Purchase price (USD) × USD/NIS rate on sale date     [same rate as proceeds]
Cost B = Shares × Purchase price (USD) × USD/NIS rate on purchase date  [actual rate paid]
```

**Step 3 — Calculate two results, compare, apply the rule**
```
Result A = Proceeds − Cost A
Result B = Proceeds − Cost B
```

| Scenario | Tax Treatment |
|---|---|
| Both A and B are **positive** (gains) | Taxable gain = the **lower** of the two |
| Both A and B are **negative** (losses) | Deductible loss = the **lower** of the two (closer to zero) |
| A and B have **opposite signs** | **Zero event** — no tax liability and no deductible loss |

The rule always selects the result closest to zero: for gains this means less tax; for losses it limits the deductible amount; for the mixed case, no tax consequence in either direction.

### 3.3 Worked Examples

**Example A — USD strengthened during holding (3.20 → 3.50), stock up**
Buy 100 shares @ $10, sell @ $12

| | NIS |
|---|---|
| Proceeds | 100 × $12 × 3.50 = ₪4,200 |
| Cost A (at sale rate 3.50) | 100 × $10 × 3.50 = ₪3,500 → Result A = **+₪700** |
| Cost B (at purchase rate 3.20) | 100 × $10 × 3.20 = ₪3,200 → Result B = **+₪1,000** |
| Both positive → taxable | Lower = **₪700** (₪300 currency gain not taxed) |

**Example B — USD weakened during holding (3.50 → 3.20), small stock gain**
Buy 100 shares @ $10, sell @ $10.50

| | NIS |
|---|---|
| Proceeds | 100 × $10.50 × 3.20 = ₪3,360 |
| Cost A (at sale rate 3.20) | 100 × $10 × 3.20 = ₪3,200 → Result A = **+₪160** |
| Cost B (at purchase rate 3.50) | 100 × $10 × 3.50 = ₪3,500 → Result B = **−₪140** |
| Opposite signs → | **Zero event** (no tax, no deductible loss) |

**Example C — USD weakened (3.50 → 3.20), stock down**
Buy 100 shares @ $10, sell @ $8

| | NIS |
|---|---|
| Proceeds | 100 × $8 × 3.20 = ₪2,560 |
| Cost A (at sale rate 3.20) | 100 × $10 × 3.20 = ₪3,200 → Result A = **−₪640** |
| Cost B (at purchase rate 3.50) | 100 × $10 × 3.50 = ₪3,500 → Result B = **−₪940** |
| Both negative → deductible | Closer to zero = **−₪640** (₪300 currency loss not deductible) |

### 3.4 Inflationary Gain Adjustment

For shares purchased **before January 1, 2003**, a portion of the gain may be classified as "inflationary gain" (רווח אינפלציוני) and taxed at a reduced rate (10%) or exempt. For shares purchased **after January 1, 2003**, the entire gain is taxed at the standard capital gains rate. In practice, most modern IBKR positions will not involve pre-2003 lots.

---

## 4. Lot Selection Method (FIFO vs. Specific Identification)

### 4.1 Default: FIFO

The Israeli Tax Ordinance (פקודת מס הכנסה) defaults to **FIFO (First In, First Out)** — the oldest shares are assumed to be sold first.

### 4.2 Specific Lot Identification

Taxpayers **may select specific lots** to sell, provided:
- The specific lots are clearly identified **at the time of the sale** (not retroactively).
- The selection is documented and consistent.

This is the core optimization lever: by choosing which lot to sell, the taxpayer can control the cost basis and the effective gain or loss recognized.

**Key strategy implications:**
- To **minimize tax**: sell lots with the highest NIS cost basis first (highest gain absorbed, lowest net gain).
- To **harvest a loss**: sell lots that are currently underwater in NIS terms, to offset gains elsewhere.
- To **defer tax**: avoid selling lots with large embedded gains; sell lots with lower gains or losses instead.

---

## 5. Loss Offsetting Rules

### 5.1 Within the Same Tax Year

Current-year capital losses from share sales can offset **capital gains, interest income, and dividend income** within the same tax year, without limitation. Only the net amount is subject to tax.

### 5.2 Loss Carryforward

If total losses exceed total gains in a given year, the **excess loss can be carried forward** to future tax years (indefinitely, until used). Losses cannot be carried back to prior years.

**Critical limitation:** Carried-forward losses from prior years can only offset **capital gains** in subsequent years — they cannot be used to offset interest income or dividend income. This is narrower than current-year losses (which offset all three). The distinction matters when deciding whether to realize a loss in the current year or defer it.

### 5.3 Cross-Asset and Cross-Border Offsetting

Capital losses from shares can also offset:
- Gains from other securities (bonds, ETFs, etc.)
- Gains from real estate sales (partial, subject to conditions)

**Cross-border ordering rule:** Foreign securities losses must first be used to offset **foreign gains** before they can be applied against Israeli (TASE) gains. The order is mandatory, not elective.

Losses **cannot** offset regular income (salary, business income).

---

## 6. Foreign Tax Credit

If tax was withheld abroad on dividends or capital gains (e.g., 15% US withholding tax on dividends under the US–Israel tax treaty), that amount can be **credited against the Israeli tax liability** for the same income. The credit cannot exceed the Israeli tax due on that specific income item.

---

## 7. Dividends

- Dividends from foreign shares are taxed at **25%** (or 30% for substantial shareholders).
- The dividend amount must be converted to NIS using the Bank of Israel rate on the **payment date**.
- Foreign withholding tax (e.g., 15% on US stocks) is credited against the Israeli tax.

---

## 8. Reporting Obligations

### 8.1 Annual Tax Return

Israeli residents with a foreign brokerage account are generally **required to file an annual tax return** (דוח שנתי) even if all taxes owed are zero. This applies if:
- Total foreign income (dividends + capital gains) exceeds a threshold set annually by the Tax Authority, or
- The taxpayer is otherwise required to file (e.g., high income, multiple income sources).

### 8.2 What to Report

For each sale during the tax year:
- Security name and ISIN
- Purchase date(s) and price(s)
- Sale date and price
- NIS cost basis and NIS proceeds
- Net gain or loss in NIS
- Any foreign tax paid on the same income

### 8.3 Exchange Rates

Use the **Bank of Israel representative exchange rate** (שער יציג) published for each relevant date.

---

## 9. Key Tax Optimization Strategies (Summary)

| Strategy | How It Reduces Tax |
|---|---|
| **Sell high-NIS-cost-basis lots first** | Reduces the recognized gain on each sale |
| **Harvest losses** | Offsets gains, reducing net taxable income |
| **Account for USD/NIS rate when harvesting losses** | Determines whether a position produces a deductible loss, a zero event, or a taxable gain under the three-step formula. A zero event (one result positive, one negative) yields no tax deduction — adjusting timing or price may shift it into a deductible loss zone |
| **Avoid breaching the 10% threshold** | Keeps the tax rate at 25% instead of 30% |
| **Use carryforward losses** | Apply prior-year losses to reduce current-year tax |
| **Maximize foreign tax credit** | Ensure all withheld taxes abroad are properly credited |

---

## 10. Out of Scope (Not Covered Here)

- RSUs and stock options from an employer (different tax treatment)
- Shares in Israeli companies (traded on TASE or dual-listed)
- Crypto assets
- Section 102 employee share plans
