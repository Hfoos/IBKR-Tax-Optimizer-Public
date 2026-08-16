# IBKR Tax Optimizer

A Streamlit web app that helps Israeli tax residents optimize which positions to sell from their Interactive Brokers (IBKR) account — minimizing capital gains tax while reaching a target cash amount.

---

## What It Does

Given a target amount you want to raise (in NIS), the app:

1. Parses your IBKR activity statement CSV exports
2. Reconstructs your open positions with full lot history (FIFO)
3. Fetches current prices (Yahoo Finance) and exchange rates (Bank of Israel API)
4. Applies the Israeli three-step tax formula to each lot
5. Recommends which positions to sell and in what order to minimize tax

**Optimization logic:** Loss positions are sold first (they reduce taxable income), then zero-event positions, then gain positions ordered by lowest effective tax rate.

**FIFO is mandatory per Israeli law** — lot order within each security is fixed. Optimization only decides *which* securities to sell.

---

## Israeli Tax Rules Applied

- **Tax rate:** 25% on net capital gains
- **Three-step formula:** Calculates Result A (using today's FX rate) and Result B (using the purchase-date FX rate) to determine the taxable amount
- **Cross-position offsetting:** Losses from one position offset gains from another within the same tax year
- **Carryforward losses:** Prior-year losses can be applied to reduce current-year gains

---

## Setup

### Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

### Data

Place your IBKR activity statement CSV exports in the `data/` folder. The app accepts multiple files covering different years. File naming convention from IBKR: `U<account>_<year>_activity.csv`.

> **Note:** The `data/` folder is excluded from this repository (.gitignore). Your personal financial data never leaves your machine.

### Run

```bash
streamlit run app.py
```

---

## Usage

1. Open the app in your browser (Streamlit will launch it automatically)
2. In the **sidebar**, enter:
   - Target amount to raise (NIS, gross before tax)
   - Prior-year carryforward loss, if any
3. Review your **current holdings** and auto-fetched prices
4. Override any prices that failed to load automatically
5. Click **Run Optimizer**
6. Review the recommended sell list and tax summary

---

## Project Structure

```
├── app.py                              # Streamlit UI
├── src/
│   ├── parser.py                       # Parses IBKR CSV activity statements
│   ├── portfolio.py                    # Builds FIFO lot queues per security
│   ├── optimizer.py                    # Greedy tax-minimizing sell selector
│   ├── tax_engine.py                   # Israeli three-step tax formula
│   └── exchange_rates.py               # Bank of Israel API client (USD/GBP/NIS)
├── data/                               # Your IBKR CSV files (not in repo)
├── requirements.txt
└── .gitignore
```

---

## Limitations

- Projections exclude sale commissions (typically < 0.1% of proceeds)
- Transferred lots use IBKR's reported cost basis at transfer date — verify with your tax advisor if original purchase records differ
- Corporate actions, mergers, and symbol renames may require manual review
- This tool is for planning purposes only — consult a licensed Israeli tax advisor before filing

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI |
| `yfinance` | Current market prices |
| `requests` | Bank of Israel exchange rate API |
| `pandas` | CSV parsing |
