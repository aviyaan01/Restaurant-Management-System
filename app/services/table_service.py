from app.extensions import db
from app.models.table import Table, Space
from app.models.order import Order
from app.utils.audit import log_audit

VALID_TABLE_STATUSES = {'open', 'occupied'}

def set_table_status(table_id: int, status: str, restaurant_id: int, user_id: int = None) -> Table:
    """
    Service method for updating table occupancy status.
    Reusable by:
      - POS Dine In order creation (Step 7): transitions table to 'occupied'
      - POS Bill payment or order cancellation (Step 8): releases table back to 'open'
      - Admin & Cashier live table board: manual status toggle
    Enforces Non-Negotiable Rule 1 (tenant boundary) and Rule 5 (AuditLog tracking).
    """
    if status not in VALID_TABLE_STATUSES:
        raise ValueError(f"Invalid table status '{status}'. Must be one of: {VALID_TABLE_STATUSES}")

    table = Table.query.filter_by(
        id=table_id,
        restaurant_id=restaurant_id
    ).first()

    if not table:
        raise ValueError(f"Table #{table_id} not found for restaurant #{restaurant_id}.")

    old_status = table.status
    if old_status != status:
        table.status = status
        db.session.commit()

        # Non-negotiable Rule 5: Audit log
        log_audit(
            action='TABLE_STATUS_CHANGED',
            record_type='Table',
            record_id=table.id,
            details={
                'table_name': table.name,
                'space_id': table.space_id,
                'old_status': old_status,
                'new_status': status
            },
            user_id=user_id,
            restaurant_id=restaurant_id
        )

    return table

def can_delete_table(table_id: int, restaurant_id: int) -> tuple[bool, str]:
    """
    Safety invariant: Prevent deleting a table that is currently occupied or has open orders.
    """
    table = Table.query.filter_by(id=table_id, restaurant_id=restaurant_id).first()
    if not table:
        return False, "Table not found."

    if table.status == 'occupied':
        return False, f"Table '{table.name}' is currently marked as occupied. Please release or clear the table first."

    # Check for active open orders
    open_order = Order.query.filter_by(
        restaurant_id=restaurant_id,
        table_id=table.id,
        status='open'
    ).first()

    if open_order:
        return False, f"Table '{table.name}' has an active open order (#{open_order.order_no}). Complete, pay, or cancel the order first."

    return True, ""

def can_delete_space(space_id: int, restaurant_id: int) -> tuple[bool, str]:
    """
    Safety invariant: Prevent deleting a dining space if any table inside is occupied or has open orders.
    """
    space = Space.query.filter_by(id=space_id, restaurant_id=restaurant_id).first()
    if not space:
        return False, "Space not found."

    # Check for occupied tables
    occupied_table = Table.query.filter_by(
        restaurant_id=restaurant_id,
        space_id=space.id,
        status='occupied'
    ).first()
    if occupied_table:
        return False, f"Cannot delete space '{space.name}' because table '{occupied_table.name}' is currently occupied."

    # Check for any tables with open orders
    open_order_table = Table.query.join(Order, Table.id == Order.table_id).filter(
        Table.restaurant_id == restaurant_id,
        Table.space_id == space.id,
        Order.status == 'open'
    ).first()
    if open_order_table:
        return False, f"Cannot delete space '{space.name}' because table '{open_order_table.name}' has an open order."

    return True, ""
