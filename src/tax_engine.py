"""
Applies the Israeli three-step formula to determine the taxable result of a sale.

Three-step formula (per Israeli tax law):
  Step 1: proceeds_nis = qty × sale_price × sale_rate − sale_commission_nis
  Step 2: cost_a = qty × cost_per_share_foreign × sale_rate   (same rate as proceeds)
          cost_b = qty × cost_per_share_foreign × purchase_rate (actual rate paid)
  Step 3: result_a = proceeds_nis − cost_a
          result_b = proceeds_nis − cost_b

  Decision:
    Both positive  → taxable gain  = min(result_a, result_b)
    Both negative  → deductible loss = max(result_a, result_b)  [closest to zero]
    Opposite signs → zero event: no tax, no deductible loss
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .portfolio import Lot

TAX_RATE = 0.25


class EventType(Enum):
    GAIN = "Gain"
    LOSS = "Loss"
    ZERO = "Zero event"


@dataclass
class LotSaleResult:
    symbol: str
    purchase_date: date
    currency: str
    qty_sold: float
    proceeds_nis: float
    result_a_nis: float
    result_b_nis: float
    taxable_nis: float      # positive = gain, negative = loss, 0 = zero event
    event_type: EventType
    gross_tax_nis: float    # tax before any cross-position offsets (0 for loss/zero)


def compute_lot_sale(
    lot: Lot,
    qty_sold: float,
    sale_price_foreign: float,
    sale_rate: float,          # current NIS rate for the lot's currency
    sale_commission_nis: float,
) -> LotSaleResult:
    """Compute the three-step tax result for selling qty_sold shares from a lot."""
    proceeds_nis = qty_sold * sale_price_foreign * sale_rate - sale_commission_nis

    cost_per_share = lot.cost_per_share_foreign
    cost_a = qty_sold * cost_per_share * sale_rate
    cost_b = qty_sold * cost_per_share * lot.purchase_rate

    result_a = proceeds_nis - cost_a
    result_b = proceeds_nis - cost_b

    if result_a >= 0 and result_b >= 0:
        taxable = min(result_a, result_b)
        event_type = EventType.GAIN
    elif result_a <= 0 and result_b <= 0:
        taxable = max(result_a, result_b)   # closest to zero (less negative)
        event_type = EventType.LOSS
    else:
        taxable = 0.0
        event_type = EventType.ZERO

    gross_tax = taxable * TAX_RATE if event_type == EventType.GAIN else 0.0

    return LotSaleResult(
        symbol=lot.symbol,
        purchase_date=lot.purchase_date,
        currency=lot.currency,
        qty_sold=qty_sold,
        proceeds_nis=proceeds_nis,
        result_a_nis=result_a,
        result_b_nis=result_b,
        taxable_nis=taxable,
        event_type=event_type,
        gross_tax_nis=gross_tax,
    )


def net_tax(
    lot_results: list[LotSaleResult],
    carryforward_loss_nis: float,
    ytd_gains_nis: float = 0.0,
    ytd_losses_nis: float = 0.0,
) -> float:
    """
    Compute the net tax after cross-position offsetting and carryforward.

    Includes already-realized YTD gains/losses so the proposed sales are taxed
    in the context of the full tax year, not in isolation.
    Returns the NIS amount owed (0 if losses exceed gains).
    """
    proposed_gains = sum(r.taxable_nis for r in lot_results if r.event_type == EventType.GAIN)
    proposed_losses = sum(abs(r.taxable_nis) for r in lot_results if r.event_type == EventType.LOSS)
    total_gains = ytd_gains_nis + proposed_gains
    total_losses = ytd_losses_nis + proposed_losses
    net_gain = total_gains - total_losses - abs(carryforward_loss_nis)
    return max(0.0, net_gain) * TAX_RATE
