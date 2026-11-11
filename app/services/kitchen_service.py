from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.extensions import db
from app.models.order import Order, OrderItem
from app.models.table import Table
from app.utils.audit import log_audit

VALID_KITCHEN_STATUSES = {'new', 'preparing', 'ready'}

def _calc_elapsed(created_at: datetime) -> tuple[int, int, str]:
    """
    Computes elapsed seconds, elapsed minutes, and urgency tier.
    Handles both timezone-aware and naive timestamps cleanly.
    
    Urgency Tiers:
      - 'normal':  < 10 minutes (Emerald / Slate)
      - 'warning': 10 - 20 minutes (Amber)
      - 'urgent':  > 20 minutes (Rose / Red High-Contrast Alert)
    """
    if not created_at:
        return 0, 0, 'normal'

    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    delta = now - created_at
    total_seconds = max(0, int(delta.total_seconds()))
    minutes = total_seconds // 60

    if minutes >= 20:
        urgency = 'urgent'
    elif minutes >= 10:
        urgency = 'warning'
    else:
        urgency = 'normal'

    return total_seconds, minutes, urgency

def get_active_kds_tickets(restaurant_id: int) -> list[dict]:
    """
    Retrieves all active kitchen tickets for the given restaurant tenant.
    A ticket is active if it has at least one item with kitchen_status in ('new', 'preparing')
    and order.status != 'cancelled'.
    
    Ordered strictly OLDEST FIRST (created_at ASC) so chefs prioritize older tickets.
    Enforces restaurant_id isolation on every query.
    """
    # Find orders that have active kitchen items
    active_orders = (
        Order.query
        .join(OrderItem, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id == restaurant_id,
            OrderItem.restaurant_id == restaurant_id,
            Order.status != 'cancelled',
            OrderItem.kitchen_status.in_(['new', 'preparing'])
        )
        .distinct()
        .order_by(Order.created_at.asc())
        .all()
    )

    tickets = []
    for order in active_orders:
        items = order.items.all()
        active_items = [i for i in items if i.kitchen_status in ('new', 'preparing')]
        ready_items = [i for i in items if i.kitchen_status == 'ready']

        # Determine overall ticket status
        has_new = any(i.kitchen_status == 'new' for i in active_items)
        ticket_status = 'new' if has_new else 'preparing'

        total_sec, elapsed_min, urgency = _calc_elapsed(order.created_at)

        tickets.append({
            'order': order,
            'order_id': order.id,
            'order_no': order.order_no,
            'order_type': order.type,
            'table_name': order.table.name if order.table else None,
            'created_at': order.created_at,
            'elapsed_seconds': total_sec,
            'elapsed_minutes': elapsed_min,
            'urgency': urgency,
            'ticket_status': ticket_status,
            'line_items': items,
            'items': items,
            'active_items': active_items,
            'ready_items': ready_items,
            'total_count': len(items),
            'ready_count': len(ready_items),
            'has_new': has_new,
            'is_all_preparing': not has_new and len(active_items) > 0
        })

    return tickets

def get_completed_kds_tickets(restaurant_id: int, limit: int = 30) -> list[dict]:
    """
    Retrieves recently completed kitchen tickets for today.
    A ticket is completed when ALL items are marked 'ready' and order is not cancelled.
    Ordered NEWEST FIRST so the kitchen can view what was just bumped.
    """
    # Fetch non-cancelled orders belonging to restaurant
    recent_orders = (
        Order.query
        .filter(
            Order.restaurant_id == restaurant_id,
            Order.status != 'cancelled'
        )
        .order_by(Order.created_at.desc())
        .limit(limit * 2)
        .all()
    )

    completed = []
    for order in recent_orders:
        items = order.items.all()
        if not items:
            continue

        # Completed if every single item is 'ready'
        if all(i.kitchen_status == 'ready' for i in items):
            total_sec, elapsed_min, _ = _calc_elapsed(order.created_at)
            completed.append({
                'order': order,
                'order_id': order.id,
                'order_no': order.order_no,
                'order_type': order.type,
                'table_name': order.table.name if order.table else None,
                'created_at': order.created_at,
                'elapsed_minutes': elapsed_min,
                'line_items': items,
                'items': items,
                'total_count': len(items)
            })

        if len(completed) >= limit:
            break

    return completed

def bump_ticket(
    order_id: int,
    restaurant_id: int,
    user_id: int,
    target_status: str
) -> Order:
    """
    Bumps all active items of an order to the target status ('preparing' or 'ready').
    When all items become 'ready', the ticket naturally leaves the active queue.
    Writes action to AuditLog (Rule 5).
    """
    if target_status not in ('preparing', 'ready'):
        raise ValueError(f"Invalid target status '{target_status}'. Must be 'preparing' or 'ready'.")

    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.status == 'cancelled':
        raise ValueError(f"Cannot bump cancelled Order #{order.order_no}.")

    bumped_items = []
    for item in order.items.all():
        if target_status == 'preparing':
            if item.kitchen_status == 'new':
                item.kitchen_status = 'preparing'
                bumped_items.append(f"{item.dish_name_snapshot} -> preparing")
        elif target_status == 'ready':
            if item.kitchen_status != 'ready':
                item.kitchen_status = 'ready'
                bumped_items.append(f"{item.dish_name_snapshot} -> ready")

    db.session.commit()

    log_audit(
        action='KDS_TICKET_BUMPED',
        record_type='Order',
        record_id=order.id,
        details={
            'order_no': order.order_no,
            'target_status': target_status,
            'bumped_items': bumped_items,
            'total_items': order.items.count()
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return order

def bump_order_item(
    item_id: int,
    restaurant_id: int,
    user_id: int,
    target_status: str
) -> OrderItem:
    """
    Bumps an individual line item's kitchen status ('new' -> 'preparing' -> 'ready').
    Enforces tenant isolation and records an AuditLog entry.
    """
    if target_status not in VALID_KITCHEN_STATUSES:
        raise ValueError(f"Invalid kitchen status '{target_status}'.")

    item = OrderItem.query.filter_by(id=item_id, restaurant_id=restaurant_id).first()
    if not item:
        raise ValueError(f"Order item #{item_id} not found.")

    prev_status = item.kitchen_status
    item.kitchen_status = target_status
    db.session.commit()

    log_audit(
        action='KDS_ITEM_BUMPED',
        record_type='OrderItem',
        record_id=item.id,
        details={
            'order_id': item.order_id,
            'dish_name': item.dish_name_snapshot,
            'previous_status': prev_status,
            'new_status': target_status
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return item
