from decimal import Decimal, ROUND_HALF_UP
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.order import Order, OrderItem
from app.models.table import Table
from app.models.menu import Dish
from app.models.user import User
from app.services.table_service import set_table_status
from app.services.billing_service import calculate_bill
from app.utils.audit import log_audit

def calculate_order_financials(restaurant: Restaurant, items_data: list[dict], table: Table = None) -> dict:
    """
    Delegates to the standard calculate_bill engine.
    Computes dish gross prices and item discounts from PostgreSQL snapshot.
    """
    subtotal = Decimal('0.00')
    total_discount = Decimal('0.00')

    for item in items_data:
        dish_id = item['dish_id']
        qty = int(item['quantity'])
        if qty <= 0:
            continue

        dish = Dish.query.filter_by(
            id=dish_id,
            restaurant_id=restaurant.id
        ).first()

        if not dish or dish.is_archived:
            continue

        reg_price = Decimal(str(dish.price))
        disc_per_unit = Decimal(str(dish.discount or '0.00'))

        subtotal += reg_price * qty
        total_discount += disc_per_unit * qty

    cover_charge = Decimal('0.00')
    if table and table.cover_charge:
        cover_charge = Decimal(str(table.cover_charge))

    return calculate_bill(
        subtotal=subtotal,
        discount_type='flat',
        discount_value=total_discount,
        cover_charge=cover_charge,
        vat_rate=restaurant.vat_rate,
        price_mode=restaurant.price_mode
    )

def create_pos_order(
    restaurant_id: int,
    user_id: int,
    order_type: str,
    items_data: list[dict],
    table_id: int = None
) -> Order:
    """
    Creates a new Order + OrderItems with immutable price snapshots.
    Assigns sequential tenant order_no, updates table occupancy, and creates kitchen lines.
    """
    restaurant = db.session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise ValueError(f"Restaurant #{restaurant_id} not found.")

    if order_type not in ('dine_in', 'take_away', 'quick'):
        raise ValueError(f"Invalid order type '{order_type}'.")

    if not items_data:
        raise ValueError("Cannot place an order with an empty cart.")

    table = None
    if order_type == 'dine_in':
        if not table_id:
            raise ValueError("Dine In order requires selecting a dining table.")
        table = Table.query.filter_by(id=table_id, restaurant_id=restaurant_id).first()
        if not table:
            raise ValueError("Selected dining table was not found.")

        # Check for existing open order on this table
        existing_order = Order.query.filter_by(
            restaurant_id=restaurant_id,
            table_id=table.id,
            status='open'
        ).first()

        if existing_order:
            # Table already has an open order -> append new items instead of crashing
            return append_items_to_pos_order(existing_order.id, restaurant_id, user_id, items_data)

    # Next sequential order_no for this restaurant tenant
    max_no = db.session.query(db.func.max(Order.order_no)).filter_by(
        restaurant_id=restaurant_id
    ).scalar() or 0
    next_order_no = max_no + 1

    # Server-side pricing recalculation
    fin = calculate_order_financials(restaurant, items_data, table)

    order = Order(
        restaurant_id=restaurant_id,
        order_no=next_order_no,
        type=order_type,
        table_id=table.id if table else None,
        status='open',
        subtotal=fin['subtotal'],
        discount=fin['discount'],
        cover_charge=fin['cover_charge'],
        vat_amount=fin['vat_amount'],
        total=fin['total'],
        payment_status='unpaid',
        created_by=user_id
    )
    db.session.add(order)
    db.session.flush()

    # Build OrderItems with name & price snapshots
    created_items_summary = []
    for item in items_data:
        dish_id = item['dish_id']
        qty = int(item['quantity'])
        if qty <= 0:
            continue

        dish = Dish.query.filter_by(id=dish_id, restaurant_id=restaurant_id).first()
        if not dish or dish.is_archived:
            raise ValueError(f"Dish #{dish_id} is no longer available on the menu.")
        if not dish.is_available:
            raise ValueError(f"Dish '{dish.name}' is currently marked unavailable.")

        effective_unit_price = max(
            Decimal('0.00'),
            Decimal(str(dish.price)) - Decimal(str(dish.discount or '0.00'))
        )

        order_item = OrderItem(
            restaurant_id=restaurant_id,
            order_id=order.id,
            dish_id=dish.id,
            dish_name_snapshot=dish.name,
            unit_price_snapshot=effective_unit_price,
            quantity=qty,
            note=item.get('note', '').strip() if item.get('note') else None,
            kitchen_status='new'
        )
        db.session.add(order_item)
        created_items_summary.append(f"{dish.name} x{qty}")

    # Set table status to Occupied if Dine In
    if table:
        set_table_status(table.id, 'occupied', restaurant_id, user_id)

    db.session.commit()

    # Non-negotiable Rule 5: Audit Log
    log_audit(
        action='ORDER_CREATED',
        record_type='Order',
        record_id=order.id,
        details={
            'order_no': order.order_no,
            'type': order.type,
            'table_id': order.table_id,
            'items_count': len(created_items_summary),
            'items': created_items_summary[:5],
            'total': float(order.total)
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return order

def append_items_to_pos_order(
    order_id: int,
    restaurant_id: int,
    user_id: int,
    new_items_data: list[dict]
) -> Order:
    """
    Appends new items to an existing open Dine In order.
    New items enter with kitchen_status = 'new'.
    Recalculates financial totals and writes to AuditLog.
    Paid orders can be modified only by a manager or owner (Rule: audited change).
    """
    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.status == 'cancelled':
        raise ValueError(f"Cannot add items to cancelled Order #{order.order_no}.")

    user = db.session.get(User, user_id)
    is_modifying_paid = (order.status == 'paid')
    if is_modifying_paid:
        if not user or user.role not in ('owner', 'manager'):
            raise PermissionError("Paid orders can be changed only by a manager or owner.")

    if not new_items_data:
        raise ValueError("No items provided to append.")

    restaurant = db.session.get(Restaurant, restaurant_id)
    table = db.session.get(Table, order.table_id) if order.table_id else None

    appended_summary = []
    for item in new_items_data:
        dish_id = item['dish_id']
        qty = int(item['quantity'])
        if qty <= 0:
            continue

        dish = Dish.query.filter_by(id=dish_id, restaurant_id=restaurant_id).first()
        if not dish or dish.is_archived:
            raise ValueError(f"Dish #{dish_id} is no longer on the menu.")
        if not dish.is_available:
            raise ValueError(f"Dish '{dish.name}' is currently unavailable.")

        effective_unit_price = max(
            Decimal('0.00'),
            Decimal(str(dish.price)) - Decimal(str(dish.discount or '0.00'))
        )

        order_item = OrderItem(
            restaurant_id=restaurant_id,
            order_id=order.id,
            dish_id=dish.id,
            dish_name_snapshot=dish.name,
            unit_price_snapshot=effective_unit_price,
            quantity=qty,
            note=item.get('note', '').strip() if item.get('note') else None,
            kitchen_status='new'
        )
        db.session.add(order_item)
        appended_summary.append(f"{dish.name} x{qty}")

    db.session.flush()

    # Recalculate totals across ALL items belonging to this order
    all_order_items = OrderItem.query.filter_by(order_id=order.id).all()
    all_items_payload = [
        {'dish_id': oi.dish_id, 'quantity': oi.quantity, 'note': oi.note}
        for oi in all_order_items if oi.dish_id
    ]

    previous_total = order.total
    fin = calculate_order_financials(restaurant, all_items_payload, table)
    order.subtotal = fin['subtotal']
    order.discount = fin['discount']
    order.cover_charge = fin['cover_charge']
    order.vat_amount = fin['vat_amount']
    order.total = fin['total']

    # If the order was previously marked paid, check if new balance is due
    paid_sum = sum(
        Decimal(str(p.amount))
        for p in order.payments.all()
        if p.status == 'completed'
    )
    if order.total > paid_sum:
        order.status = 'open'
        order.payment_status = 'partial' if paid_sum > Decimal('0.00') else 'unpaid'
        if order.table_id:
            set_table_status(order.table_id, 'occupied', restaurant_id, user_id)

    db.session.commit()

    action_name = 'PAID_ORDER_MODIFIED' if is_modifying_paid else 'ORDER_ITEMS_APPENDED'
    log_audit(
        action=action_name,
        record_type='Order',
        record_id=order.id,
        details={
            'order_no': order.order_no,
            'appended_items': appended_summary,
            'previous_total': float(previous_total),
            'new_total': float(order.total),
            'modified_by_role': user.role if user else 'unknown'
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return order

def cancel_pos_order(
    order_id: int,
    restaurant_id: int,
    user_id: int,
    reason: str
) -> Order:
    """
    Cancels an order with a mandatory cancellation reason.
    Restricted to Managers and Owners.
    Releases table status if it was a Dine In order.
    Paid orders can be cancelled only by a manager or owner (audited as PAID_ORDER_CANCELLED).
    """
    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.status == 'cancelled':
        raise ValueError(f"Order #{order.order_no} is already cancelled.")

    user = db.session.get(User, user_id)
    is_cancelling_paid = (order.status == 'paid')
    if is_cancelling_paid:
        if not user or user.role not in ('owner', 'manager'):
            raise PermissionError("Paid orders can be cancelled only by a manager or owner.")

    clean_reason = (reason or '').strip()
    if len(clean_reason) < 5:
        raise ValueError("Cancellation reason is mandatory and must be at least 5 characters.")

    previous_status = order.status
    order.status = 'cancelled'
    order.cancel_reason = clean_reason

    # Release table if Dine In
    if order.table_id:
        other_open = Order.query.filter(
            Order.table_id == order.table_id,
            Order.id != order.id,
            Order.status == 'open'
        ).first()
        if not other_open:
            set_table_status(order.table_id, 'open', restaurant_id, user_id)

    db.session.commit()

    action_name = 'PAID_ORDER_CANCELLED' if is_cancelling_paid else 'ORDER_CANCELLED'
    log_audit(
        action=action_name,
        record_type='Order',
        record_id=order.id,
        details={
            'order_no': order.order_no,
            'previous_status': previous_status,
            'type': order.type,
            'table_id': order.table_id,
            'reason': clean_reason,
            'total': float(order.total)
        },
        user_id=user_id,
        restaurant_id=restaurant_id
    )

    return order

