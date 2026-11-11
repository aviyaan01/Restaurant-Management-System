from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.utils.decorators import role_required
from app.services.kitchen_service import (
    get_active_kds_tickets,
    get_completed_kds_tickets,
    bump_ticket,
    bump_order_item
)

kitchen_bp = Blueprint('kitchen', __name__, url_prefix='/kitchen')

@kitchen_bp.route('/')
@login_required
@role_required('owner', 'manager', 'kitchen')
def display():
    """
    Kitchen Display System (KDS): Live KOT orders queue and bump bar.
    Restricted to Kitchen staff, Managers, and Owners.
    """
    tab = request.args.get('tab', 'active')
    active_tickets = get_active_kds_tickets(current_user.restaurant_id)
    completed_tickets = get_completed_kds_tickets(current_user.restaurant_id) if tab == 'history' else []

    return render_template(
        'kitchen/display.html',
        active_tab=tab,
        tickets=active_tickets,
        completed_tickets=completed_tickets,
        active_count=len(active_tickets)
    )

@kitchen_bp.route('/tickets')
@login_required
@role_required('owner', 'manager', 'kitchen')
def ticket_feed():
    """
    Lightweight HTMX polling endpoint (polled every 1.5 - 2s).
    Returns the reactive active tickets grid fragment.
    Strictly isolated by current_user.restaurant_id (Rule 1).
    """
    tickets = get_active_kds_tickets(current_user.restaurant_id)
    return render_template('kitchen/_ticket_grid.html', tickets=tickets)

@kitchen_bp.route('/history-feed')
@login_required
@role_required('owner', 'manager', 'kitchen')
def history_feed():
    """
    HTMX endpoint returning today's completed tickets fragment.
    """
    completed_tickets = get_completed_kds_tickets(current_user.restaurant_id)
    return render_template('kitchen/_history_list.html', completed_tickets=completed_tickets)

@kitchen_bp.route('/tickets/<int:order_id>/bump', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'kitchen')
def bump_ticket_route(order_id):
    """
    Bumps all items of an order to 'preparing' or 'ready'.
    Returns updated ticket grid for HTMX swap.
    """
    target_status = request.form.get('target_status', 'preparing')
    try:
        bump_ticket(
            order_id=order_id,
            restaurant_id=current_user.restaurant_id,
            user_id=current_user.id,
            target_status=target_status
        )
    except Exception as e:
        flash(f"Could not bump ticket: {str(e)}", "danger")

    if request.headers.get('HX-Request'):
        tickets = get_active_kds_tickets(current_user.restaurant_id)
        return render_template('kitchen/_ticket_grid.html', tickets=tickets)

    return redirect(url_for('kitchen.display'))

@kitchen_bp.route('/items/<int:item_id>/bump', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'kitchen')
def bump_item_route(item_id):
    """
    Bumps an individual line item's status.
    Returns updated ticket grid for HTMX swap.
    """
    target_status = request.form.get('target_status', 'ready')
    try:
        bump_order_item(
            item_id=item_id,
            restaurant_id=current_user.restaurant_id,
            user_id=current_user.id,
            target_status=target_status
        )
    except Exception as e:
        flash(f"Could not bump item: {str(e)}", "danger")

    if request.headers.get('HX-Request'):
        tickets = get_active_kds_tickets(current_user.restaurant_id)
        return render_template('kitchen/_ticket_grid.html', tickets=tickets)

    return redirect(url_for('kitchen.display'))
