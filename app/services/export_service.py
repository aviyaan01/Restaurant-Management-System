import csv
import io
from datetime import datetime, date, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from app.models.order import Order
from app.models.finance import FinanceEntry

def export_finance_csv(
    restaurant_id: int,
    entry_type: str = 'all',
    start_date: date = None,
    end_date: date = None
) -> str:
    """
    Exports filtered financial cashbook records to CSV.
    CRITICAL REQUIREMENT: Exported totals MUST equal on-screen cashbook totals exactly.
    """
    query = FinanceEntry.query.filter_by(restaurant_id=restaurant_id)

    if entry_type and entry_type != 'all':
        query = query.filter(FinanceEntry.type == entry_type)

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        query = query.filter(FinanceEntry.entry_date >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        query = query.filter(FinanceEntry.entry_date <= end_dt)

    entries = query.order_by(FinanceEntry.entry_date.desc(), FinanceEntry.id.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Column Headers
    writer.writerow([
        "ID",
        "Date Time (UTC)",
        "Type",
        "Source",
        "Amount (BDT)",
        "Description",
        "Staff"
    ])

    sales_total = Decimal('0.00')
    purchases_total = Decimal('0.00')
    expenses_total = Decimal('0.00')

    for entry in entries:
        dt_str = entry.entry_date.strftime('%Y-%m-%d %H:%M:%S') if entry.entry_date else ""
        source_str = f"POS Order #{entry.order.order_no if entry.order else entry.order_id}" if entry.order_id else "Manual Entry"
        staff_name = entry.creator.name if entry.creator else "System"
        amt = entry.amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if entry.type == 'sale':
            sales_total += amt
        elif entry.type == 'purchase':
            purchases_total += amt
        elif entry.type == 'expense':
            expenses_total += amt

        writer.writerow([
            entry.id,
            dt_str,
            entry.type.title(),
            source_str,
            f"{amt:.2f}",
            entry.note or "",
            staff_name
        ])

    net_balance = sales_total - (purchases_total + expenses_total)

    # Summary section matching on-screen totals exactly
    writer.writerow([])
    writer.writerow(["SUMMARY (FILTERED VIEW)", "", "", "", "", "", ""])
    writer.writerow(["Total Sales (BDT)", "", "", "", f"{sales_total:.2f}", "", ""])
    writer.writerow(["Total Purchases (BDT)", "", "", "", f"{purchases_total:.2f}", "", ""])
    writer.writerow(["Total Expenses (BDT)", "", "", "", f"{expenses_total:.2f}", "", ""])
    writer.writerow(["Net Balance (BDT)", "", "", "", f"{net_balance:.2f}", "", ""])

    return output.getvalue()

def export_orders_csv(
    restaurant_id: int,
    status: str = None,
    order_type: str = None,
    staff_id: int = None,
    start_date: date = None,
    end_date: date = None,
    order_no: int = None
) -> str:
    """
    Exports filtered orders directory records to CSV.
    CRITICAL REQUIREMENT: Exported totals MUST equal on-screen order totals exactly.
    """
    query = Order.query.filter_by(restaurant_id=restaurant_id)

    if status and status != 'all':
        query = query.filter(Order.status == status)

    if order_type and order_type != 'all':
        query = query.filter(Order.type == order_type)

    if staff_id:
        try:
            sid = int(staff_id)
            if sid > 0:
                query = query.filter(Order.created_by == sid)
        except (ValueError, TypeError):
            pass

    if order_no:
        try:
            ono = int(order_no)
            query = query.filter(Order.order_no == ono)
        except (ValueError, TypeError):
            pass

    if start_date:
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        query = query.filter(Order.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        query = query.filter(Order.created_at <= end_dt)

    orders = query.order_by(Order.created_at.desc(), Order.order_no.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Column Headers
    writer.writerow([
        "Order #",
        "Date Time (UTC)",
        "Type",
        "Table",
        "Status",
        "Payment Status",
        "Subtotal (BDT)",
        "Discount (BDT)",
        "Cover Charge (BDT)",
        "VAT (BDT)",
        "Total (BDT)",
        "Staff"
    ])

    subtotal_sum = Decimal('0.00')
    discount_sum = Decimal('0.00')
    cover_charge_sum = Decimal('0.00')
    vat_sum = Decimal('0.00')
    total_sum = Decimal('0.00')

    for o in orders:
        dt_str = o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else ""
        table_name = o.table.name if o.table else "-"
        staff_name = o.creator.name if o.creator else "System"

        sub = o.subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        disc = o.discount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cov = o.cover_charge.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        vat = o.vat_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tot = o.total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        subtotal_sum += sub
        discount_sum += disc
        cover_charge_sum += cov
        vat_sum += vat
        total_sum += tot

        writer.writerow([
            o.order_no,
            dt_str,
            o.type.replace('_', ' ').title(),
            table_name,
            o.status.title(),
            o.payment_status.title(),
            f"{sub:.2f}",
            f"{disc:.2f}",
            f"{cov:.2f}",
            f"{vat:.2f}",
            f"{tot:.2f}",
            staff_name
        ])

    # Summary Row matching on-screen totals exactly
    writer.writerow([])
    writer.writerow([
        "TOTAL",
        "",
        "",
        "",
        "",
        f"{len(orders)} orders",
        f"{subtotal_sum:.2f}",
        f"{discount_sum:.2f}",
        f"{cover_charge_sum:.2f}",
        f"{vat_sum:.2f}",
        f"{total_sum:.2f}",
        ""
    ])

    return output.getvalue()

