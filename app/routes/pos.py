from decimal import Decimal
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.user import User
from app.models.audit import AuditLog
from app.forms.order import OrderCancelForm, OrderFilterForm
from app.forms.payment import PaymentForm
from app.services.order_service import (
    calculate_order_financials,
    create_pos_order,
    append_items_to_pos_order,
    cancel_pos_order
)
from app.services.billing_service import record_order_payment
from app.utils.decorators import role_required

pos_bp = Blueprint('pos', __name__, url_prefix='/pos')

# ==============================================================================
# SESSION CART HELPERS
# ==============================================================================

def _get_cart():
    cart = session.get('pos_cart')
    if not isinstance(cart, dict):
        cart = {
            'order_type': 'quick',
            'table_id': None,
            'existing_order_id': None,
            'items': {}
        }
        session['pos_cart'] = cart
    return cart

def _save_cart(cart):
    session['pos_cart'] = cart
    session.modified = True

def _build_cart_view():
    cart = _get_cart()
    items_data = list(cart.get('items', {}).values())

    table = None
    if cart.get('order_type') == 'dine_in' and cart.get('table_id'):
        table = Table.query.filter_by(
            id=cart['table_id'],
            restaurant_id=current_user.restaurant_id
        ).first()

    fin = calculate_order_financials(current_user.restaurant, items_data, table)

    detailed_items = []
    for item in items_data:
        dish = Dish.query.filter_by(
            id=item['dish_id'],
            restaurant_id=current_user.restaurant_id
        ).first()
        if dish and not dish.is_archived:
            eff_price = max(
                Decimal('0.00'),
                Decimal(str(dish.price)) - Decimal(str(dish.discount or '0.00'))
            )
            qty = int(item['quantity'])
            detailed_items.append({
                'dish': dish,
                'dish_id': dish.id,
                'name': dish.name,
                'effective_price': eff_price,
                'quantity': qty,
                'note': item.get('note', ''),
                'line_total': eff_price * qty
            })

    existing_order = None
    if cart.get('existing_order_id'):
        existing_order = Order.query.filter_by(
            id=cart['existing_order_id'],
            restaurant_id=current_user.restaurant_id,
            status='open'
        ).first()

    return {
        'cart': cart,
        'items': detailed_items,
        'item_count': sum(i['quantity'] for i in detailed_items),
        'financials': fin,
        'table': table,
        'existing_order': existing_order
    }

# ==============================================================================
# MAIN POS REGISTER TERMINAL
# ==============================================================================

@pos_bp.route('/')
@login_required
@role_required('owner', 'manager', 'cashier')
def terminal():
    """
    Main POS Register Screen.
    Touch-first, responsive, designed for 10-inch tablets and desktop terminals.
    """
    categories = Category.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Category.sort_order.asc(), Category.name.asc()).all()

    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    tables = Table.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Table.space_id.asc(), Table.name.asc()).all()

    # Pre-map open orders to table ids for quick lookup
    open_orders = Order.query.filter_by(
        restaurant_id=current_user.restaurant_id,
        status='open'
    ).filter(Order.table_id.isnot(None)).all()
    open_orders_map = {o.table_id: o for o in open_orders}

    # Query active menu dishes (archived hidden)
    selected_cat_id = request.args.get('category_id', type=int)
    search_q = request.args.get('q', '').strip()

    dish_query = Dish.query.filter(
        Dish.restaurant_id == current_user.restaurant_id,
        Dish.is_archived.is_(False)
    )
    if selected_cat_id:
        dish_query = dish_query.filter(Dish.category_id == selected_cat_id)
    if search_q:
        dish_query = dish_query.filter(Dish.name.ilike(f"%{search_q}%"))

    dishes = dish_query.order_by(Dish.name.asc()).all()
    cart_view = _build_cart_view()

    return render_template(
        'pos/terminal.html',
        categories=categories,
        dishes=dishes,
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        selected_category_id=selected_cat_id,
        search_query=search_q,
        **cart_view
    )

@pos_bp.route('/catalog')
@login_required
@role_required('owner', 'manager', 'cashier')
def catalog_partial():
    """HTMX partial returning filtered dish cards for the left catalog pane."""
    selected_cat_id = request.args.get('category_id', type=int)
    search_q = request.args.get('q', '').strip()

    query = Dish.query.filter(
        Dish.restaurant_id == current_user.restaurant_id,
        Dish.is_archived.is_(False)
    )
    if selected_cat_id:
        query = query.filter(Dish.category_id == selected_cat_id)
    if search_q:
        query = query.filter(Dish.name.ilike(f"%{search_q}%"))

    dishes = query.order_by(Dish.name.asc()).all()

    return render_template(
        'pos/_catalog.html',
        dishes=dishes,
        selected_category_id=selected_cat_id,
        search_query=search_q
    )

@pos_bp.route('/tables')
@login_required
@role_required('owner', 'manager', 'cashier')
def tables():
    """
    Live visual table status board for Cashiers and POS operators.
    Directs to the live status floor board.
    """
    return redirect(url_for('admin.table_board'))

# ==============================================================================
# REACTIVE CART HTMX ACTIONS
# ==============================================================================

@pos_bp.route('/cart/add/<int:dish_id>', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def cart_add(dish_id):
    """Adds a dish to the active session cart or increments quantity."""
    dish = Dish.query.filter_by(
        id=dish_id,
        restaurant_id=current_user.restaurant_id,
        is_archived=False
    ).first_or_404()

    if not dish.is_available:
        flash(f"'{dish.name}' is currently unavailable.", "warning")
        cart_view = _build_cart_view()
        return render_template('pos/_cart.html', **cart_view)

    cart = _get_cart()
    key = str(dish.id)
    if key in cart['items']:
        cart['items'][key]['quantity'] += 1
    else:
        cart['items'][key] = {
            'dish_id': dish.id,
            'quantity': 1,
            'note': ''
        }

    _save_cart(cart)
    cart_view = _build_cart_view()

    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Table.space_id.asc(), Table.name.asc()).all()
    open_orders_map = {o.table_id: o for o in Order.query.filter_by(restaurant_id=current_user.restaurant_id, status='open').filter(Order.table_id.isnot(None)).all()}

    return render_template(
        'pos/_cart.html',
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        **cart_view
    )

@pos_bp.route('/cart/update-qty/<int:dish_id>', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def cart_update_qty(dish_id):
    """Adjusts line item quantity (+1, -1, or remove)."""
    cart = _get_cart()
    key = str(dish_id)
    action = request.form.get('action')

    if key in cart['items']:
        if action == 'inc':
            cart['items'][key]['quantity'] += 1
        elif action == 'dec':
            cart['items'][key]['quantity'] -= 1
            if cart['items'][key]['quantity'] <= 0:
                del cart['items'][key]
        elif action == 'remove':
            del cart['items'][key]

    _save_cart(cart)
    cart_view = _build_cart_view()

    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Table.space_id.asc(), Table.name.asc()).all()
    open_orders_map = {o.table_id: o for o in Order.query.filter_by(restaurant_id=current_user.restaurant_id, status='open').filter(Order.table_id.isnot(None)).all()}

    return render_template(
        'pos/_cart.html',
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        **cart_view
    )

@pos_bp.route('/cart/update-note/<int:dish_id>', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def cart_update_note(dish_id):
    """Sets special preparation instructions for a specific line item."""
    cart = _get_cart()
    key = str(dish_id)
    note = request.form.get('note', '').strip()

    if key in cart['items']:
        cart['items'][key]['note'] = note[:255]

    _save_cart(cart)
    cart_view = _build_cart_view()

    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Table.space_id.asc(), Table.name.asc()).all()
    open_orders_map = {o.table_id: o for o in Order.query.filter_by(restaurant_id=current_user.restaurant_id, status='open').filter(Order.table_id.isnot(None)).all()}

    return render_template(
        'pos/_cart.html',
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        **cart_view
    )

@pos_bp.route('/cart/set-type', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def cart_set_type():
    """Switches order mode (Quick, Take Away, Dine In) and manages table selection."""
    cart = _get_cart()
    order_type = request.form.get('order_type', 'quick')
    table_id = request.form.get('table_id', type=int)

    if order_type in ('quick', 'take_away', 'dine_in'):
        cart['order_type'] = order_type

    if order_type == 'dine_in' and table_id:
        cart['table_id'] = table_id
        # Detect if this table has an active open order to append to
        open_order = Order.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            table_id=table_id,
            status='open'
        ).first()
        cart['existing_order_id'] = open_order.id if open_order else None
    else:
        if order_type != 'dine_in':
            cart['table_id'] = None
            cart['existing_order_id'] = None

    _save_cart(cart)
    cart_view = _build_cart_view()

    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Table.space_id.asc(), Table.name.asc()).all()
    open_orders_map = {o.table_id: o for o in Order.query.filter_by(restaurant_id=current_user.restaurant_id, status='open').filter(Order.table_id.isnot(None)).all()}

    return render_template(
        'pos/_cart.html',
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        **cart_view
    )

@pos_bp.route('/cart/clear', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def cart_clear():
    """Clears the active POS cart."""
    session.pop('pos_cart', None)
    cart_view = _build_cart_view()

    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()
    tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Table.space_id.asc(), Table.name.asc()).all()
    open_orders_map = {o.table_id: o for o in Order.query.filter_by(restaurant_id=current_user.restaurant_id, status='open').filter(Order.table_id.isnot(None)).all()}

    return render_template(
        'pos/_cart.html',
        spaces=spaces,
        tables=tables,
        open_orders_map=open_orders_map,
        **cart_view
    )

# ==============================================================================
# PLACE ORDER (DOUBLE-CLICK PROTECTED, PRICE RECALCULATED ON SERVER)
# ==============================================================================

@pos_bp.route('/order/place', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def order_place():
    """
    Submits cart to database.
    Calculates prices strictly from database records (never trusts browser payload).
    Supports new orders and appending to existing open Dine In table orders.
    """
    cart = _get_cart()
    items_data = list(cart.get('items', {}).values())

    if not items_data:
        flash("Cannot place an order with an empty cart.", "danger")
        return redirect(url_for('pos.terminal'))

    order_type = cart.get('order_type', 'quick')
    table_id = cart.get('table_id')

    try:
        if cart.get('existing_order_id'):
            order = append_items_to_pos_order(
                order_id=cart['existing_order_id'],
                restaurant_id=current_user.restaurant_id,
                user_id=current_user.id,
                new_items_data=items_data
            )
            flash(f"Order #{order.order_no} updated! Appended {len(items_data)} new item(s) to table.", "success")
        else:
            order = create_pos_order(
                restaurant_id=current_user.restaurant_id,
                user_id=current_user.id,
                order_type=order_type,
                items_data=items_data,
                table_id=table_id
            )
            flash(f"Order #{order.order_no} placed successfully!", "success")

        # Clear cart on successful order
        session.pop('pos_cart', None)

        if request.headers.get('HX-Request'):
            response = redirect(url_for('pos.order_detail', order_id=order.id))
            response.headers['HX-Redirect'] = url_for('pos.order_detail', order_id=order.id)
            return response

        return redirect(url_for('pos.order_detail', order_id=order.id))

    except Exception as e:
        flash(f"Could not place order: {str(e)}", "danger")
        if request.headers.get('HX-Request'):
            cart_view = _build_cart_view()
            return render_template('pos/_cart.html', **cart_view)
        return redirect(url_for('pos.terminal'))

# ==============================================================================
# ORDERS DIRECTORY & ORDER DETAILS
# ==============================================================================

@pos_bp.route('/orders')
@login_required
@role_required('owner', 'manager', 'cashier')
def order_list():
    """
    Comprehensive orders listing with multi-parameter search, filtering, and pagination.
    Accessible to Cashiers, Managers, and Owners.
    """
    page = request.args.get('page', 1, type=int)
    search_q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('type', '').strip()
    staff_filter = request.args.get('staff_id', type=int)
    date_filter = request.args.get('date', '').strip()

    query = Order.query.filter(Order.restaurant_id == current_user.restaurant_id)

    if search_q:
        clean_no = search_q.lstrip('#')
        if clean_no.isdigit():
            query = query.filter(Order.order_no == int(clean_no))

    if status_filter:
        query = query.filter(Order.status == status_filter)

    if type_filter:
        query = query.filter(Order.type == type_filter)

    if staff_filter:
        query = query.filter(Order.created_by == staff_filter)

    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Order.created_at) == target_date)
        except ValueError:
            pass

    pagination = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )

    staff_members = User.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(User.name.asc()).all()

    return render_template(
        'pos/orders/index.html',
        pagination=pagination,
        orders=pagination.items,
        staff_members=staff_members,
        search_query=search_q,
        status_filter=status_filter,
        type_filter=type_filter,
        staff_filter=staff_filter,
        date_filter=date_filter
    )

@pos_bp.route('/orders/<int:order_id>')
@login_required
@role_required('owner', 'manager', 'cashier')
def order_detail(order_id):
    """
    Full order detail inspection screen.
    Displays immutable item snapshots, notes, kitchen status, tax details, and timeline.
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    cancel_form = OrderCancelForm()

    return render_template(
        'pos/orders/detail.html',
        order=order,
        cancel_form=cancel_form
    )

@pos_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def order_cancel(order_id):
    """
    Cancels an open order with mandatory reason.
    Restricted to Owners and Managers only (Cashier gets 403 Forbidden).
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    form = OrderCancelForm()
    if form.validate_on_submit():
        try:
            cancel_pos_order(
                order_id=order.id,
                restaurant_id=current_user.restaurant_id,
                user_id=current_user.id,
                reason=form.reason.data
            )
            flash(f"Order #{order.order_no} has been cancelled successfully.", "info")
        except Exception as e:
            flash(f"Could not cancel order: {str(e)}", "danger")
    else:
        flash(form.reason.errors[0] if form.reason.errors else "Invalid cancellation request.", "danger")

    return redirect(url_for('pos.order_detail', order_id=order.id))

@pos_bp.route('/orders/<int:order_id>/append', methods=['GET'])
@login_required
@role_required('owner', 'manager', 'cashier')
def order_append_redirect(order_id):
    """
    Helper to jump from Order Detail straight into the POS terminal
    with the table and existing order loaded into the cart.
    Paid orders can be modified only by managers/owners.
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    if order.status == 'cancelled':
        flash("Cannot add items to a cancelled order.", "warning")
        return redirect(url_for('pos.order_detail', order_id=order.id))

    if order.status == 'paid' and current_user.role not in ('owner', 'manager'):
        flash("Paid orders can be changed only by a manager or owner.", "danger")
        return redirect(url_for('pos.order_detail', order_id=order.id))

    cart = _get_cart()
    cart['order_type'] = order.type
    cart['table_id'] = order.table_id
    cart['existing_order_id'] = order.id
    _save_cart(cart)

    msg = f"Loaded Order #{order.order_no} into cart. Select dishes to append to the order."
    if order.status == 'paid':
        msg = f"[Manager Override] Modifying paid Order #{order.order_no}. Additional items will require payment."
    flash(msg, "info")
    return redirect(url_for('pos.terminal'))

# ==============================================================================
# BILLING & MANUAL PAYMENT RECORDING
# ==============================================================================

@pos_bp.route('/orders/<int:order_id>/pay', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def order_pay(order_id):
    """
    Payment checkout and recording screen.
    Supports Cash, bKash, Nagad, Card, and multi-method split payments.
    Computes cash tendered change due live.
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    if order.status == 'cancelled':
        flash(f"Cannot record payment for cancelled Order #{order.order_no}.", "danger")
        return redirect(url_for('pos.order_detail', order_id=order.id))

    # Calculate already paid total
    completed_payments = order.payments.filter_by(status='completed').order_by(Payment.created_at.desc()).all()
    already_paid = sum(Decimal(str(p.amount)) for p in completed_payments)
    remaining_due = max(Decimal('0.00'), order.total - already_paid)

    if order.status == 'paid' and remaining_due <= Decimal('0.00'):
        flash(f"Order #{order.order_no} is already fully paid and closed.", "info")
        return redirect(url_for('pos.order_detail', order_id=order.id))

    form = PaymentForm()

    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                res = record_order_payment(
                    order_id=order.id,
                    restaurant_id=current_user.restaurant_id,
                    received_by_id=current_user.id,
                    method=form.method.data,
                    amount=form.amount.data,
                    reference=form.reference.data,
                    cash_received=form.cash_received.data if form.method.data == 'cash' else None
                )

                if res['is_fully_paid']:
                    change_msg = f" | Change Due: ৳{res['change_due']:.2f}" if res['change_due'] > 0 else ""
                    flash(f"Order #{order.order_no} is fully paid via {form.method.data.upper()}!{change_msg}", "success")
                    return redirect(url_for('pos.order_detail', order_id=order.id))
                else:
                    flash(f"Partial payment of ৳{res['actual_payment']:.2f} recorded via {form.method.data.upper()}. Remaining balance due: ৳{res['remaining_due']:.2f}", "info")
                    return redirect(url_for('pos.order_pay', order_id=order.id))

            except Exception as e:
                flash(f"Payment failed: {str(e)}", "danger")
        else:
            first_err = next(iter(form.errors.values()))[0] if form.errors else "Please verify the payment form details."
            flash(f"Validation error: {first_err}", "danger")

    # On GET or failed POST, set default amount to remaining due
    if request.method == 'GET':
        form.amount.data = remaining_due

    return render_template(
        'pos/orders/pay.html',
        order=order,
        form=form,
        already_paid=already_paid,
        remaining_due=remaining_due,
        completed_payments=completed_payments
    )

# ==============================================================================
# PRINTING: CUSTOMER RECEIPT & KITCHEN ORDER TICKET (KOT)
# ==============================================================================

@pos_bp.route('/orders/<int:order_id>/receipt')
@login_required
@role_required('owner', 'manager', 'cashier')
def order_receipt(order_id):
    """
    Print-optimized Customer Sales Receipt view.
    Supports 80mm and 58mm thermal paper roll widths.
    Strictly tenant-isolated by restaurant_id (Non-Negotiable Rule 1).
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    width = request.args.get('width', '80')
    if width not in ('80', '58'):
        width = '80'

    autoprint = request.args.get('autoprint', '0') == '1'

    # Completed payment records
    completed_payments = order.payments.filter_by(status='completed').order_by(Payment.created_at.asc()).all()
    total_paid = sum(Decimal(str(p.amount)) for p in completed_payments)

    # Calculate change due from AuditLog or difference
    change_due = Decimal('0.00')
    audit = AuditLog.query.filter_by(
        restaurant_id=current_user.restaurant_id,
        record_id=order.id,
        action='ORDER_FULLY_PAID'
    ).order_by(AuditLog.id.desc()).first()

    if audit and audit.details and 'change_due' in audit.details:
        change_due = Decimal(str(audit.details['change_due']))
    elif total_paid > order.total:
        change_due = total_paid - order.total

    return render_template(
        'pos/printing/receipt.html',
        order=order,
        restaurant=current_user.restaurant,
        width=width,
        autoprint=autoprint,
        completed_payments=completed_payments,
        total_paid=total_paid,
        change_due=change_due
    )

@pos_bp.route('/orders/<int:order_id>/kot')
@login_required
@role_required('owner', 'manager', 'cashier', 'kitchen')
def order_kot(order_id):
    """
    Print-optimized Kitchen Order Ticket (KOT) slip.
    Contains ONLY kitchen items, quantities, and preparation notes (STRICTLY NO PRICES/AMOUNTS).
    Supports 80mm and 58mm thermal paper widths.
    """
    order = Order.query.filter_by(
        id=order_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    width = request.args.get('width', '80')
    if width not in ('80', '58'):
        width = '80'

    autoprint = request.args.get('autoprint', '0') == '1'

    return render_template(
        'pos/printing/kot.html',
        order=order,
        restaurant=current_user.restaurant,
        width=width,
        autoprint=autoprint,
        items=order.items.all()
    )
