"""
IBKR Tax Optimizer — Streamlit App

Inputs (sidebar):
  - Target NIS amount to raise (gross, before tax)
  - Optional prior-year carryforward loss (NIS)

Auto-loaded:
  - All IBKR activity CSVs from the /data folder
  - Current prices via Yahoo Finance (with manual override option)
  - USD/GBP exchange rates via Bank of Israel API

Output:
  - Recommended sell list (FIFO within each security)
  - Tax summary: proceeds, gains, losses, net tax owed
"""

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))

from src.parser import parse_all_csvs, get_csv_filenames, parse_open_positions
from src.portfolio import build_portfolio
from src.exchange_rates import get_rate, prefetch_rates
from src.optimizer import optimize, OptimizationResult, compute_manual_sale
from src.tax_engine import EventType
from src.realized import compute_ytd_realized

# Use /data subfolder if it contains CSVs; otherwise fall back to project root
_data_sub = Path(__file__).parent / "data"
_data_root = Path(__file__).parent
DATA_FOLDER = str(_data_sub if list(_data_sub.glob("*.csv")) else _data_root)

# Yahoo Finance ticker suffixes to try for LSE-listed ETFs.
# Bare ticker ("") is last — some symbols (e.g. SWRD) collide with unrelated
# OTC/pink-sheets US stocks that would otherwise be picked up first.
_YF_SUFFIXES = [".L", ".AS", ".SW", ""]

# Some LSE ETFs are quoted in GBX (pence) on Yahoo — divide by 100
_GBX_SYMBOLS = {"SMEA", "CSPX", "SWRD", "IUFS", "EIMI", "IUIT"}


def fetch_price(symbol: str, currency: str) -> float | None:
    """Try Yahoo Finance with common exchange suffixes. Returns price in original currency."""
    for suffix in _YF_SUFFIXES:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
            info = ticker.fast_info
            price = info.last_price
            if price and price > 0:
                # If Yahoo returns a GBX price for a GBP-quoted stock, convert
                if currency == "GBP" and symbol in _GBX_SYMBOLS and price > 500:
                    price = price / 100
                return float(price)
        except Exception:
            continue
    return None


def format_nis(value: float) -> str:
    return f"₪{value:,.0f}"


def format_qty(value: float) -> str:
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.4f}"


def build_selections(
    editor_rows: list[dict],
    position_keys: list[tuple[str, str]],
    portfolio: dict,
) -> dict[tuple[str, str], float]:
    """Convert st.data_editor output (a list of dicts) into a selections mapping."""
    selections: dict[tuple[str, str], float] = {}
    for i, (account, symbol) in enumerate(position_keys):
        total_held = sum(lot.remaining_qty for lot in portfolio[(account, symbol)])
        qty = max(0.0, min(float(editor_rows[i]["Shares to sell"]), total_held))
        if qty > 1e-9:
            selections[(account, symbol)] = qty
    return selections


def event_badge(event_type: EventType) -> str:
    if event_type == EventType.GAIN:
        return "🔴 Gain"
    elif event_type == EventType.LOSS:
        return "🟢 Loss"
    else:
        return "⚪ Zero event"


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="IBKR Tax Optimizer",
    page_icon="📊",
    layout="wide",
)
st.title("IBKR Tax Optimizer")
st.caption("Israeli tax optimization for Interactive Brokers accounts")

# ── Sidebar: inputs ───────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Inputs")

    mode = st.radio(
        "Mode",
        ["Raise target amount", "Select positions manually"],
    )

    if mode == "Raise target amount":
        target_nis = st.number_input(
            "Target amount to raise (NIS, gross before tax)",
            min_value=0,
            value=100_000,
            step=5_000,
            format="%d",
        )
    else:
        target_nis = 0

    carryforward_nis = st.number_input(
        "Prior-year carryforward loss (NIS) — optional",
        min_value=0,
        value=0,
        step=1_000,
        format="%d",
        help="Enter 0 if unknown or not applicable.",
    )


# ── Load CSV files ────────────────────────────────────────────────────────────

def data_folder_path() -> Path:
    target = _data_sub if _data_sub.exists() else _data_root
    target.mkdir(parents=True, exist_ok=True)
    return target


def data_folder_url() -> str:
    return data_folder_path().resolve().as_uri()


def no_csv_message() -> str:
    return (
        "No CSV files found in the `data/` folder. Place your IBKR activity statements "
        "here"
    )


def open_data_folder() -> None:
    target = data_folder_path()
    try:
        if os.name == "nt":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception:
        pass


csv_names = get_csv_filenames(DATA_FOLDER)
if not csv_names:
    st.markdown(no_csv_message())
    if st.button("Open /data folder"):
        open_data_folder()
    st.stop()

with st.expander(f"Loaded {len(csv_names)} activity file(s)", expanded=False):
    for name in csv_names:
        st.write(f"• {name}")

# ── Parse & build portfolio ───────────────────────────────────────────────────

with st.spinner("Parsing transactions and fetching exchange rates..."):
    try:
        transactions = parse_all_csvs(DATA_FOLDER)
        raw_portfolio = build_portfolio(transactions)
        open_positions = parse_open_positions(DATA_FOLDER)
        from datetime import date as _date
        ytd = compute_ytd_realized(transactions, _date.today().year)
    except Exception as e:
        st.error(f"Failed to parse CSV files: {e}")
        st.stop()

if not raw_portfolio:
    st.warning("No open positions found after processing all transactions.")
    st.stop()

# ── Auto-filter against Open Positions (most recent CSV) ─────────────────────
# The Trades-only parser cannot see corporate actions, account transfers, or
# symbol renames. The Open Positions section is IBKR's authoritative list.

auto_excluded = {}
if open_positions:
    for (account, sym) in list(raw_portfolio.keys()):
        account_positions = open_positions.get(account, {})
        if sym not in account_positions:
            auto_excluded[(account, sym)] = raw_portfolio.pop((account, sym))

portfolio = raw_portfolio

if auto_excluded:
    with st.expander(
        f"⚠ {len(auto_excluded)} position(s) auto-excluded (not in IBKR Open Positions)",
        expanded=False,
    ):
        st.caption(
            "These symbols appear in trade history but are absent from the most recent "
            "IBKR activity statement's Open Positions section. Likely causes: corporate "
            "action (merger/SPAC), account transfer, or symbol rename."
        )
        for (account, sym), queue in auto_excluded.items():
            total = sum(lot.remaining_qty for lot in queue)
            st.write(f"• **{account} — {sym}** — {total:.4f} shares (reconstructed from trades, not confirmed by IBKR)")

# ── Manual exclusion ──────────────────────────────────────────────────────────

with st.sidebar:
    if mode == "Raise target amount":
        st.divider()
        st.subheader("Exclude positions")
        st.caption("Remove specific positions from the optimization.")
        all_options = sorted(f"{account} — {sym}" for (account, sym) in portfolio.keys())
        excluded_manual = st.multiselect(
            "Exclude from optimization",
            options=all_options,
            default=[],
            help="Selected positions will be ignored by the optimizer.",
        )
    else:
        excluded_manual = []

for opt in excluded_manual:
    account, sym = opt.split(" — ", 1)
    portfolio.pop((account, sym), None)

if not portfolio:
    st.warning("All positions have been excluded. Nothing to optimize.")
    st.stop()

# ── Show current holdings ─────────────────────────────────────────────────────

st.subheader("Current Holdings")

holding_rows = []
for (account, symbol), queue in portfolio.items():
    total_shares = sum(lot.remaining_qty for lot in queue)
    transfer_shares = sum(lot.remaining_qty for lot in queue if lot.is_transfer)
    num_lots = len(queue)
    currency = queue[0].currency
    notes = "⚠ includes transferred lots*" if transfer_shares > 0 else ""
    holding_rows.append({
        "Account": account,
        "Symbol": symbol,
        "Currency": currency,
        "Shares held": format_qty(total_shares),
        "Lots (FIFO layers)": num_lots,
        "Oldest lot date": min(lot.purchase_date for lot in queue).isoformat(),
        "Notes": notes,
    })

if excluded_manual:
    st.caption(f"Showing {len(portfolio)} of {len(portfolio) + len(excluded_manual)} positions ({', '.join(excluded_manual)} manually excluded).")

st.dataframe(holding_rows, use_container_width=True, hide_index=True)

has_transfer_lots = any(lot.is_transfer for q in portfolio.values() for lot in q)
if has_transfer_lots:
    st.caption(
        "\\* Transferred lots: cost basis is IBKR's reported value at transfer date, "
        "not the original acquisition price. Verify with your tax advisor if the "
        "original purchase records differ."
    )

# ── Manual position selector ──────────────────────────────────────────────────

if mode == "Select positions manually":
    st.subheader("Shares to Sell")
    st.caption("Enter how many shares to sell for each position. Positions with 0 are ignored.")
    position_keys = list(portfolio.keys())
    editor_data = []
    for (account, symbol) in position_keys:
        queue = portfolio[(account, symbol)]
        total_held = sum(lot.remaining_qty for lot in queue)
        editor_data.append({
            "Account": account,
            "Symbol": symbol,
            "Shares held": format_qty(total_held),
            "Shares to sell": 0.0,
        })
    edited_df = st.data_editor(
        editor_data,
        column_config={
            "Shares to sell": st.column_config.NumberColumn(
                min_value=0, step=0.0001, format="%.4f"
            ),
        },
        disabled=["Account", "Symbol", "Shares held"],
        use_container_width=True,
        hide_index=True,
    )

# ── Fetch current prices ──────────────────────────────────────────────────────

st.subheader("Current Prices")

# Prices are per unique symbol (same stock has the same price across accounts)
symbols = list(dict.fromkeys(sym for (_, sym) in portfolio.keys()))
currencies = {}
for (_, sym), queue in portfolio.items():
    if sym not in currencies:
        currencies[sym] = queue[0].currency

auto_prices: dict[str, float | None] = {}
with st.spinner("Fetching current prices from Yahoo Finance..."):
    for sym in symbols:
        auto_prices[sym] = fetch_price(sym, currencies[sym])

# Allow manual overrides in sidebar
price_overrides: dict[str, float] = {}
with st.sidebar:
    st.divider()
    st.subheader("Price overrides")
    st.caption("Leave at 0 to use auto-fetched price.")
    for sym in symbols:
        auto = auto_prices.get(sym)
        hint = f"Auto: {auto:.4f}" if auto else "Auto-fetch failed"
        override = st.number_input(
            f"{sym} ({currencies[sym]}) — {hint}",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.4f",
            key=f"override_{sym}",
        )
        if override > 0:
            price_overrides[sym] = override

final_prices: dict[str, float] = {}
price_issues = []
for sym in symbols:
    if sym in price_overrides:
        final_prices[sym] = price_overrides[sym]
    elif auto_prices.get(sym):
        final_prices[sym] = auto_prices[sym]
    else:
        price_issues.append(sym)

if price_issues:
    st.warning(
        f"Could not fetch prices for: {', '.join(price_issues)}. "
        "Enter them manually in the sidebar."
    )

price_display = []
for sym in symbols:
    price_display.append({
        "Symbol": sym,
        "Currency": currencies[sym],
        "Price": f"{final_prices[sym]:.4f}" if sym in final_prices else "⚠ Missing",
        "Source": "Manual override" if sym in price_overrides else ("Yahoo Finance" if auto_prices.get(sym) else "—"),
    })
st.dataframe(price_display, use_container_width=True, hide_index=True)

if price_issues and set(price_issues) & set(symbols):
    missing = set(price_issues) & set(final_prices.keys() ^ set(symbols))
    if missing:
        st.error(f"Cannot run optimizer — prices missing for: {', '.join(missing)}")
        st.stop()

# ── Fetch current exchange rates ──────────────────────────────────────────────

needed_currencies = list(set(currencies.values()))
current_rates: dict[str, float] = {}
rate_errors = []

with st.spinner("Fetching current exchange rates from Bank of Israel..."):
    from datetime import date
    today = date.today()
    for cur in needed_currencies:
        try:
            current_rates[cur] = get_rate(cur, today)
        except Exception as e:
            rate_errors.append(f"{cur}: {e}")

if rate_errors:
    st.warning("Exchange rate fetch issues:\n" + "\n".join(rate_errors))
    for cur in needed_currencies:
        if cur not in current_rates:
            manual_rate = st.number_input(
                f"Enter current {cur}/NIS rate manually",
                min_value=0.0,
                value=3.65 if cur == "USD" else 4.60,
                step=0.001,
                format="%.4f",
            )
            current_rates[cur] = manual_rate

rate_display = [{"Currency": cur, "NIS Rate": f"{rate:.4f}"} for cur, rate in current_rates.items()]
st.caption(f"Exchange rates as of {today.isoformat()}: " + ", ".join(f"{r['Currency']}/NIS = {r['NIS Rate']}" for r in rate_display))

# ── Year-to-date realized P&L ─────────────────────────────────────────────────

st.subheader("Year-to-date Realized P&L")
if ytd.sale_count == 0:
    st.info(f"No sales found in {_date.today().year}. YTD P&L baseline is zero.")
else:
    ytd_col1, ytd_col2, ytd_col3 = st.columns(3)
    ytd_col1.metric(f"Realized gains ({_date.today().year})", format_nis(ytd.gains_nis))
    ytd_col2.metric(f"Realized losses ({_date.today().year})", format_nis(ytd.losses_nis))
    ytd_col3.metric("Net YTD", format_nis(ytd.gains_nis - ytd.losses_nis),
                    delta=None)
    st.caption(
        f"Based on {ytd.sale_count} sell transaction(s) already executed this year. "
        "These are factored into the tax calculation below."
    )
    with st.expander(f"View sell details ({len(ytd.details)} lot(s))", expanded=False):
        detail_rows = []
        for d in ytd.details:
            detail_rows.append({
                "Sale date": d.sale_date.isoformat(),
                "Account": d.account,
                "Symbol": d.symbol,
                "Lot purchased": d.purchase_date.isoformat(),
                "Qty sold": format_qty(d.qty_sold),
                "Currency": d.currency,
                "Proceeds (NIS)": format_nis(d.proceeds_nis),
                "Taxable (NIS)": format_nis(d.taxable_nis),
                "Event": event_badge(d.event_type),
            })
        st.dataframe(detail_rows, use_container_width=True, hide_index=True)

# ── Run optimizer ─────────────────────────────────────────────────────────────

st.divider()

_button_label = "▶ Calculate Tax" if mode == "Select positions manually" else "▶ Run Optimizer"
if st.button(_button_label, type="primary", use_container_width=True):
    if not final_prices:
        st.error("No prices available. Enter prices manually in the sidebar.")
        st.stop()

    if mode == "Select positions manually":
        selections = build_selections(edited_df, position_keys, portfolio)
        if not selections:
            st.warning("No shares selected. Enter quantities to sell and click ▶ Calculate Tax.")
            st.stop()
        with st.spinner("Calculating tax..."):
            st.session_state["opt_result"] = compute_manual_sale(
                selections=selections,
                portfolio=portfolio,
                current_prices=final_prices,
                current_rates=current_rates,
                carryforward_loss_nis=float(carryforward_nis),
                ytd_gains_nis=ytd.gains_nis,
                ytd_losses_nis=ytd.losses_nis,
            )
    else:
        with st.spinner("Optimizing sell order..."):
            st.session_state["opt_result"] = optimize(
                portfolio=portfolio,
                current_prices=final_prices,
                current_rates=current_rates,
                target_nis=float(target_nis),
                carryforward_loss_nis=float(carryforward_nis),
                ytd_gains_nis=ytd.gains_nis,
                ytd_losses_nis=ytd.losses_nis,
            )

if "opt_result" in st.session_state:
    result: OptimizationResult = st.session_state["opt_result"]

    # ── Summary metrics ───────────────────────────────────────────────────────

    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gross proceeds", format_nis(result.total_proceeds_nis))
    col2.metric("Net tax owed (25%)", format_nis(result.net_tax_nis))
    col3.metric("Net after tax", format_nis(result.total_proceeds_nis - result.net_tax_nis))
    col4.metric("Effective tax rate", f"{result.net_tax_nis / result.total_proceeds_nis * 100:.1f}%" if result.total_proceeds_nis > 0 else "0%")

    if result.remaining_carryforward_nis > 0:
        st.info(f"Remaining carryforward loss after this sale: {format_nis(result.remaining_carryforward_nis)}")

    # ── IBKR Order Summary ────────────────────────────────────────────────────

    if not result.recommendations:
        st.warning("No sell actions generated. The target may exceed your total portfolio value.")
    else:
        with st.container(border=True):
            st.subheader("IBKR Order Summary")
            st.caption("Place these orders in IBKR to execute the recommended tax-loss harvesting strategy.")

            seen_keys: list[tuple[str, str]] = []
            groups: dict[tuple[str, str], dict] = {}
            for rec in result.recommendations:
                key = (rec.account, rec.symbol)
                if key not in groups:
                    seen_keys.append(key)
                    groups[key] = {
                        "Account": rec.account,
                        "Symbol": rec.symbol,
                        "Currency": rec.currency,
                        "_shares": rec.qty_to_sell,
                        "_price": rec.current_price,
                        "_proceeds_nis": rec.proceeds_nis,
                    }
                else:
                    groups[key]["_shares"] += rec.qty_to_sell
                    groups[key]["_proceeds_nis"] += rec.proceeds_nis

            order_rows = []
            for key in seen_keys:
                g = groups[key]
                total_held = sum(lot.remaining_qty for lot in portfolio[key])
                is_full_close = abs(g["_shares"] - total_held) < 1e-4
                order_rows.append({
                    "Account": g["Account"],
                    "Symbol": g["Symbol"],
                    "Currency": g["Currency"],
                    "Shares to Sell": format_qty(g["_shares"]),
                    f"Price ({g['Currency']})": f"{g['_price']:.4f}",
                    "Total Proceeds (NIS)": format_nis(g["_proceeds_nis"]),
                    "Status": "⚠ Full close" if is_full_close else "",
                })
            st.dataframe(order_rows, use_container_width=True, hide_index=True)

        # ── Lot-level detail ──────────────────────────────────────────────────

        st.subheader("Recommended Sell Actions")
        rows = []
        for rec in result.recommendations:
            rows.append({
                "Account": rec.account,
                "Symbol": rec.symbol,
                "Lot purchased": rec.purchase_date.isoformat(),
                "Shares to sell": format_qty(rec.qty_to_sell),
                f"Price ({rec.currency})": f"{rec.current_price:.4f}",
                "Proceeds (NIS)": format_nis(rec.proceeds_nis),
                "Result A — cost @ sale-day rate (NIS)": format_nis(rec.result_a_nis),
                "Result B — cost @ purchase-day rate (NIS)": format_nis(rec.result_b_nis),
                "Taxable (NIS)": format_nis(rec.taxable_nis),
                "Event": event_badge(rec.event_type),
                "Gross tax (NIS)": format_nis(rec.gross_tax_nis),
            })
        st.caption("Click a row to see the step-by-step calculation for that lot.")
        selection = st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
        )

        selected_indices = selection.selection.rows if selection.selection else []
        if selected_indices:
            rec = result.recommendations[selected_indices[0]]
            cost_per_share = rec.purchase_price + rec.purchase_commission / rec.original_qty
            cost_a_nis = rec.proceeds_nis - rec.result_a_nis
            cost_b_nis = rec.proceeds_nis - rec.result_b_nis

            with st.container(border=True):
                st.markdown(
                    f"**Calculation detail — {rec.symbol} · Lot purchased {rec.purchase_date.isoformat()}**"
                )

                col_a, col_b, col_c = st.columns(3)

                with col_a:
                    st.markdown("**Proceeds**")
                    st.write(f"Shares sold: `{rec.qty_to_sell:,.4f}`")
                    st.write(f"Sale price: `{rec.current_price:.4f} {rec.currency}`")
                    st.write(f"Sale-day rate: `{rec.sale_rate:.4f} NIS/{rec.currency}`")
                    st.write(f"Formula: `qty × price × rate`")
                    st.markdown(f"**Proceeds (NIS): {format_nis(rec.proceeds_nis)}**")

                with col_b:
                    st.markdown("**Cost A — sale-day rate**")
                    st.write(f"Purchase price/share: `{rec.purchase_price:.4f} {rec.currency}`")
                    st.write(f"Commission/share (prorated): `{rec.purchase_commission / rec.original_qty:.4f} {rec.currency}`")
                    st.write(f"Cost/share incl. commission: `{cost_per_share:.4f} {rec.currency}`")
                    st.write(f"Rate used: `{rec.sale_rate:.4f} NIS/{rec.currency}` (sale-day)")
                    st.write(f"Formula: `qty × cost/share × sale_rate`")
                    st.write(f"Cost A (NIS): {format_nis(cost_a_nis)}")
                    st.markdown(f"**Result A (NIS): {format_nis(rec.result_a_nis)}**")

                with col_c:
                    st.markdown("**Cost B — purchase-day rate**")
                    st.write(f"Purchase price/share: `{rec.purchase_price:.4f} {rec.currency}`")
                    st.write(f"Cost/share incl. commission: `{cost_per_share:.4f} {rec.currency}`")
                    st.write(f"Rate used: `{rec.purchase_rate:.4f} NIS/{rec.currency}` (purchase-day)")
                    st.write(f"Formula: `qty × cost/share × purchase_rate`")
                    st.write(f"Cost B (NIS): {format_nis(cost_b_nis)}")
                    st.markdown(f"**Result B (NIS): {format_nis(rec.result_b_nis)}**")

                st.divider()
                st.markdown("**Tax determination**")
                a = rec.result_a_nis
                b = rec.result_b_nis
                tax_col1, tax_col2 = st.columns(2)
                with tax_col1:
                    st.write(f"Result A: {format_nis(a)}")
                    st.write(f"Result B: {format_nis(b)}")
                    if a > 0 and b > 0:
                        rule = f"Both positive → taxable gain = min(A, B) = {format_nis(min(a, b))}"
                    elif a < 0 and b < 0:
                        rule = f"Both negative → deductible loss = max(A, B) = {format_nis(max(a, b))}"
                    else:
                        rule = "Opposite signs → zero event: no tax, no deductible loss"
                    st.write(f"Rule: {rule}")
                with tax_col2:
                    st.write(f"**Taxable amount (NIS):** {format_nis(rec.taxable_nis)}")
                    st.write(f"**Event type:** {event_badge(rec.event_type)}")
                    st.write(f"**Gross tax (NIS, 25%):** {format_nis(rec.gross_tax_nis)}")

    # ── Tax breakdown ─────────────────────────────────────────────────────────

    st.subheader("Tax Breakdown")
    breakdown_col1, breakdown_col2 = st.columns(2)
    with breakdown_col1:
        if result.ytd_gains_nis > 0 or result.ytd_losses_nis > 0:
            st.write(f"**YTD realized gains:** {format_nis(result.ytd_gains_nis)}")
            st.write(f"**YTD realized losses:** {format_nis(result.ytd_losses_nis)}")
            st.write(f"**Proposed gains:** {format_nis(result.total_gains_nis)}")
            st.write(f"**Proposed losses:** {format_nis(result.total_losses_nis)}")
            st.divider()
            all_gains = result.ytd_gains_nis + result.total_gains_nis
            all_losses = result.ytd_losses_nis + result.total_losses_nis
        else:
            all_gains = result.total_gains_nis
            all_losses = result.total_losses_nis
            st.write(f"**Total gains (taxable):** {format_nis(all_gains)}")
            st.write(f"**Total losses (deductible):** {format_nis(all_losses)}")
        if carryforward_nis > 0:
            st.write(f"**Prior-year carryforward applied:** {format_nis(min(float(carryforward_nis), max(0.0, all_gains - all_losses)))}")
        st.write(f"**Net taxable gain:** {format_nis(max(0.0, all_gains - all_losses - float(carryforward_nis)))}")
        st.write(f"**Tax rate:** 25%")
        st.write(f"**Tax owed:** {format_nis(result.net_tax_nis)}")
    with breakdown_col2:
        event_counts = {}
        for rec in result.recommendations:
            key = rec.event_type.value
            event_counts[key] = event_counts.get(key, 0) + 1
        for event, count in event_counts.items():
            st.write(f"**{event} positions:** {count}")
