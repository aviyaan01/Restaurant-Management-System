from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange
from sqlalchemy import func
from app.extensions import db
from app.models.finance import FinanceEntry
from app.models.order import Order, OrderItem
from app.models.table import Table
from app.utils.audit import log_audit

VALID_FINANCE_TYPES = {'sale', 'purchase', 'expense'}

def _normalize_entry_datetime(entry_date) -> datetime:
    """Normalizes a date or datetime object into a timezone-aware UTC datetime."""
    if isinstance(entry_date, datetime):
        if entry_date.tzinfo is None:
            return entry_date.replace(tzinfo=timezone.utc)
        return entry_date.astimezone(timezone.utc)
    elif isinstance(entry_date, date):
        # Attach current UTC time to preserve order of entry while respecting selected calendar day
        current_time = datetime.now(timezone.utc).time()
        return datetime.combine(entry_date, current_time, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

def _calc_comparison(today_val: Decimal, yest_val: Decimal) -> dict:
    """Computes day-over-day amount difference and percentage change."""
    diff = (today_val - yest_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if yest_val > Decimal('0.00'):
        pct = float(((today_val - yest_val) / yest_val) * Decimal('100.0'))
    elif yest_val < Decimal('0.00'):
        pct = float(((today_val - yest_val) / abs(yest_val)) * Decimal('100.0'))
    else:
        pct = 100.0 if today_val > Decimal('0.00') else (0.0 if today_val == Decimal('0.00') else -100.0)

    return {
        'value': today_val,
        'yesterday_value': yest_val,
        'diff': diff,
        'pct': round(pct, 1),
        'direction': 'up' if diff > Decimal('0.00') else ('down' if diff < Decimal('0.00') else 'flat')
    }

def create_manual_finance_entry(
    restaurant_id: int,
    user_id: int,
    entry_type: str,
    amount: Decimal,
    note: str = None,
    entry_date: date = None
) -> FinanceEntry:
    """
    Creates a manual finance ledger entry (market purchase, operational expense, or manual sale).
    Non-negotiable Rule 1: Always scoped to restaurant_id.
    Non-negotiable Rule 3: Amount stored as Numeric(12, 2) BDT (৳).
    Non-negotiable Rule 5: Writes entry to AuditLog.
    """
    clean_type = (entry_type or '').strip().lower()
    if clean_type not in VALID_FINANCE_TYPES:
        raise ValueError(f"Invalid transaction type '{entry_type}'. Must be one of: {VALID_FINANCE_TYPES}")

    amt = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if amt <= Decimal('0.00'):
        raise ValueError("Amount must be greater than zero.")

    dt = _normalize_entry_datetime(entry_date)

    entry = FinanceEntry(
        restaurant_id=restaurant_id,
        type=clean_type,
        amount=amt,
        note=(note or '').strip() or None,
        entry_date=dt,
        order_id=None,  # Manual entry: order_id is strictly None
        created_by=user_id
    )
    db.session.add(entry)
    db.session.commit()

    log_audit(
        action='FINANCE_ENTRY_CREATED',
        record_type='FinanceEntry',
        record_id=entry.id,
        details={
            'type': clean_type,
            'amount': str(amt),
            'note': entry.note,
            'entry_date': dt.isoformat()
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return entry

def update_manual_finance_entry(
    entry_id: int,
    restaurant_id: int,
    user_id: int,
    entry_type: str,
    amount: Decimal,
    note: str = None,
    entry_date: date = None
) -> FinanceEntry:
    """
    Updates a manual finance entry.
    INVARIANT: Entries automatically created from paid orders (order_id is not None)
    are strictly READ-ONLY and cannot be edited.
    """
    entry = FinanceEntry.query.filter_by(id=entry_id, restaurant_id=restaurant_id).first()
    if not entry:
        raise ValueError(f"Finance entry #{entry_id} not found.")

    if entry.order_id is not None:
        raise PermissionError(
            f"Finance entry #{entry.id} was automatically generated from POS Order #{entry.order_id} and is read-only."
        )

    clean_type = (entry_type or '').strip().lower()
    if clean_type not in VALID_FINANCE_TYPES:
        raise ValueError(f"Invalid transaction type '{entry_type}'. Must be one of: {VALID_FINANCE_TYPES}")

    amt = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if amt <= Decimal('0.00'):
        raise ValueError("Amount must be greater than zero.")

    old_details = {
        'type': entry.type,
        'amount': str(entry.amount),
        'note': entry.note,
        'entry_date': entry.entry_date.isoformat() if entry.entry_date else None
    }

    dt = _normalize_entry_datetime(entry_date)
    entry.type = clean_type
    entry.amount = amt
    entry.note = (note or '').strip() or None
    entry.entry_date = dt

    db.session.commit()

    log_audit(
        action='FINANCE_ENTRY_UPDATED',
        record_type='FinanceEntry',
        record_id=entry.id,
        details={
            'old': old_details,
            'new': {
                'type': clean_type,
                'amount': str(amt),
                'note': entry.note,
                'entry_date': dt.isoformat()
            }
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return entry

def delete_manual_finance_entry(
    entry_id: int,
    restaurant_id: int,
    user_id: int
) -> None:
    """
    Deletes a manual finance entry.
    INVARIANT: Entries automatically created from paid orders (order_id is not None)
    are strictly READ-ONLY and cannot be deleted.
    """
    entry = FinanceEntry.query.filter_by(id=entry_id, restaurant_id=restaurant_id).first()
    if not entry:
        raise ValueError(f"Finance entry #{entry_id} not found.")

    if entry.order_id is not None:
        raise PermissionError(
            f"Finance entry #{entry.id} was automatically generated from POS Order #{entry.order_id} and cannot be deleted."
        )

    entry_data = {
        'type': entry.type,
        'amount': str(entry.amount),
        'note': entry.note,
        'entry_date': entry.entry_date.isoformat() if entry.entry_date else None
    }

    db.session.delete(entry)
    db.session.commit()

    log_audit(
        action='FINANCE_ENTRY_DELETED',
        record_type='FinanceEntry',
        record_id=entry_id,
        details=entry_data,
        user_id=user_id,
        restaurant_id=restaurant_id
    )

def get_finance_cashbook(
    restaurant_id: int,
    entry_type: str = 'all',
    start_date: date = None,
    end_date: date = None,
    page: int = 1,
    per_page: int = 20
) -> dict:
    """
    Returns paginated finance entries with filters (type, date range)
    and computes daily and monthly totals for the restaurant.
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

    pagination = query.order_by(FinanceEntry.entry_date.desc(), FinanceEntry.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # Calculate Today's Totals (All types for today)
    now = datetime.now(timezone.utc)
    today = now.date()
    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    today_end = datetime.combine(today, time.max, tzinfo=timezone.utc)

    today_entries = FinanceEntry.query.filter(
        FinanceEntry.restaurant_id == restaurant_id,
        FinanceEntry.entry_date >= today_start,
        FinanceEntry.entry_date <= today_end
    ).all()

    today_sales = sum((e.amount for e in today_entries if e.type == 'sale'), Decimal('0.00'))
    today_purchases = sum((e.amount for e in today_entries if e.type == 'purchase'), Decimal('0.00'))
    today_expenses = sum((e.amount for e in today_entries if e.type == 'expense'), Decimal('0.00'))
    today_net = today_sales - (today_purchases + today_expenses)

    # Calculate Current Month Totals
    month_start = datetime(today.year, today.month, 1, 0, 0, 0, tzinfo=timezone.utc)
    _, last_day = monthrange(today.year, today.month)
    month_end = datetime(today.year, today.month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    month_entries = FinanceEntry.query.filter(
        FinanceEntry.restaurant_id == restaurant_id,
        FinanceEntry.entry_date >= month_start,
        FinanceEntry.entry_date <= month_end
    ).all()

    month_sales = sum((e.amount for e in month_entries if e.type == 'sale'), Decimal('0.00'))
    month_purchases = sum((e.amount for e in month_entries if e.type == 'purchase'), Decimal('0.00'))
    month_expenses = sum((e.amount for e in month_entries if e.type == 'expense'), Decimal('0.00'))
    month_net = month_sales - (month_purchases + month_expenses)

    return {
        'pagination': pagination,
        'entries': pagination.items,
        'daily_totals': {
            'sales': today_sales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'purchases': today_purchases.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'expenses': today_expenses.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'net': today_net.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        },
        'monthly_totals': {
            'sales': month_sales.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'purchases': month_purchases.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'expenses': month_expenses.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'net': month_net.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        }
    }

def get_dashboard_metrics(restaurant_id: int, user_role: str = 'owner') -> dict:
    """
    Computes analytics and operational dashboard metrics.
    Features:
      - Today vs Yesterday day-over-day KPI cards:
        Sales (Gross), Paid Orders, Unpaid Orders, Expenses, Purchases, Net Profit.
      - Exact reconciliation: Total Sales == Sum of FinanceEntry(type='sale').
      - Sales charts data for Chart.js:
        1. Today's hourly breakdown (00:00 to 23:00)
        2. This week's daily breakdown (7 days)
      - Top 5 selling dishes (rank, name, quantity, revenue snapshot).
      - Manager view: Operational metrics (order counts, tables) without owner-only financial totals.
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)

    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    today_end = datetime.combine(today, time.max, tzinfo=timezone.utc)

    yesterday_start = datetime.combine(yesterday, time.min, tzinfo=timezone.utc)
    yesterday_end = datetime.combine(yesterday, time.max, tzinfo=timezone.utc)

    # 1. Finance Entries for Today and Yesterday
    today_fe = FinanceEntry.query.filter(
        FinanceEntry.restaurant_id == restaurant_id,
        FinanceEntry.entry_date >= today_start,
        FinanceEntry.entry_date <= today_end
    ).all()

    yesterday_fe = FinanceEntry.query.filter(
        FinanceEntry.restaurant_id == restaurant_id,
        FinanceEntry.entry_date >= yesterday_start,
        FinanceEntry.entry_date <= yesterday_end
    ).all()

    # Sales sums (FinanceEntry type='sale')
    today_sales = sum((e.amount for e in today_fe if e.type == 'sale'), Decimal('0.00'))
    yesterday_sales = sum((e.amount for e in yesterday_fe if e.type == 'sale'), Decimal('0.00'))

    # Purchases sums (FinanceEntry type='purchase')
    today_purchases = sum((e.amount for e in today_fe if e.type == 'purchase'), Decimal('0.00'))
    yesterday_purchases = sum((e.amount for e in yesterday_fe if e.type == 'purchase'), Decimal('0.00'))

    # Expenses sums (FinanceEntry type='expense')
    today_expenses = sum((e.amount for e in today_fe if e.type == 'expense'), Decimal('0.00'))
    yesterday_expenses = sum((e.amount for e in yesterday_fe if e.type == 'expense'), Decimal('0.00'))

    # Net Profit
    today_net = today_sales - (today_purchases + today_expenses)
    yesterday_net = yesterday_sales - (yesterday_purchases + yesterday_expenses)

    # 2. Orders Metrics: Paid and Unpaid for Today and Yesterday
    # Paid Orders: orders with status == 'paid' created/paid today
    today_paid_orders = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status == 'paid',
        Order.created_at >= today_start,
        Order.created_at <= today_end
    ).all()

    yesterday_paid_orders = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status == 'paid',
        Order.created_at >= yesterday_start,
        Order.created_at <= yesterday_end
    ).all()

    today_paid_total = sum((o.total for o in today_paid_orders), Decimal('0.00'))
    yesterday_paid_total = sum((o.total for o in yesterday_paid_orders), Decimal('0.00'))
    today_paid_count = len(today_paid_orders)
    yesterday_paid_count = len(yesterday_paid_orders)

    # Unpaid Orders: orders with status != 'paid' and status != 'cancelled' created today
    today_unpaid_orders = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'paid',
        Order.status != 'cancelled',
        Order.created_at >= today_start,
        Order.created_at <= today_end
    ).all()

    yesterday_unpaid_orders = Order.query.filter(
        Order.restaurant_id == restaurant_id,
        Order.status != 'paid',
        Order.status != 'cancelled',
        Order.created_at >= yesterday_start,
        Order.created_at <= yesterday_end
    ).all()

    today_unpaid_total = sum((o.total for o in today_unpaid_orders), Decimal('0.00'))
    yesterday_unpaid_total = sum((o.total for o in yesterday_unpaid_orders), Decimal('0.00'))
    today_unpaid_count = len(today_unpaid_orders)
    yesterday_unpaid_count = len(yesterday_unpaid_orders)

    # Operational metrics
    total_orders_today = today_paid_count + today_unpaid_count
    total_orders_yesterday = yesterday_paid_count + yesterday_unpaid_count
    table_count = Table.query.filter_by(restaurant_id=restaurant_id).count()
    occupied_table_count = Table.query.filter_by(restaurant_id=restaurant_id, status='occupied').count()

    # 3. Chart 1: Today's Hourly Sales (00:00 to 23:00)
    hourly_labels = [f"{h:02d}:00" for h in range(24)]
    hourly_sales = [Decimal('0.00')] * 24

    for entry in today_fe:
        if entry.type == 'sale':
            entry_dt = entry.entry_date
            if entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)
            else:
                entry_dt = entry_dt.astimezone(timezone.utc)
            h = entry_dt.hour
            hourly_sales[h] += entry.amount

    hourly_sales_floats = [float(val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) for val in hourly_sales]

    # 4. Chart 2: This Week's Daily Sales (Past 7 Days ending Today)
    weekly_labels = []
    weekly_sales = []

    for i in range(6, -1, -1):
        day_date = today - timedelta(days=i)
        d_start = datetime.combine(day_date, time.min, tzinfo=timezone.utc)
        d_end = datetime.combine(day_date, time.max, tzinfo=timezone.utc)
        
        day_entries = FinanceEntry.query.filter(
            FinanceEntry.restaurant_id == restaurant_id,
            FinanceEntry.type == 'sale',
            FinanceEntry.entry_date >= d_start,
            FinanceEntry.entry_date <= d_end
        ).all()
        
        day_total = sum((e.amount for e in day_entries), Decimal('0.00'))
        weekly_labels.append(day_date.strftime("%a (%d/%m)"))
        weekly_sales.append(float(day_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)))

    # 5. Top 5 Selling Dishes
    # Aggregates OrderItem quantity and line revenue for non-cancelled orders of this restaurant
    top_dishes_query = (
        db.session.query(
            OrderItem.dish_name_snapshot.label('name'),
            func.sum(OrderItem.quantity).label('total_qty'),
            func.sum(OrderItem.quantity * OrderItem.unit_price_snapshot).label('total_revenue')
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.restaurant_id == restaurant_id,
            Order.status != 'cancelled'
        )
        .group_by(OrderItem.dish_name_snapshot)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    top_dishes = []
    for rank, row in enumerate(top_dishes_query, start=1):
        top_dishes.append({
            'rank': rank,
            'name': row.name,
            'quantity': int(row.total_qty or 0),
            'revenue': Decimal(str(row.total_revenue or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        })

    is_owner = (user_role == 'owner')

    kpi_cards = {
        'sales': _calc_comparison(today_sales, yesterday_sales),
        'paid': {
            'value': today_paid_total,
            'yesterday_value': yesterday_paid_total,
            'count': today_paid_count,
            'yesterday_count': yesterday_paid_count,
            'comparison': _calc_comparison(today_paid_total, yesterday_paid_total)
        },
        'unpaid': {
            'value': today_unpaid_total,
            'yesterday_value': yesterday_unpaid_total,
            'count': today_unpaid_count,
            'yesterday_count': yesterday_unpaid_count,
            'comparison': _calc_comparison(today_unpaid_total, yesterday_unpaid_total)
        },
        'expenses': _calc_comparison(today_expenses, yesterday_expenses),
        'purchases': _calc_comparison(today_purchases, yesterday_purchases),
        'net': _calc_comparison(today_net, yesterday_net),
        'orders_count': {
            'today': total_orders_today,
            'yesterday': total_orders_yesterday,
            'diff': total_orders_today - total_orders_yesterday
        },
        'tables': {
            'total': table_count,
            'occupied': occupied_table_count,
            'open': table_count - occupied_table_count,
            'occupancy_pct': round((occupied_table_count / table_count * 100) if table_count > 0 else 0.0, 1)
        }
    }

    return {
        'is_owner': is_owner,
        'kpi_cards': kpi_cards,
        'charts': {
            'hourly': {
                'labels': hourly_labels,
                'data': hourly_sales_floats
            },
            'weekly': {
                'labels': weekly_labels,
                'data': weekly_sales
            }
        },
        'top_dishes': top_dishes
    }

