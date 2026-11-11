from datetime import date, datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.finance import FinanceEntry
from app.models.audit import AuditLog
from app.forms.settings import RestaurantSettingsForm
from app.forms.staff import StaffCreateForm, StaffEditForm
from app.forms.menu import CategoryForm, DishForm
from app.forms.table import SpaceForm, TableForm, BulkTableForm
from app.forms.finance import FinanceEntryForm, FinanceFilterForm
from app.forms.audit import AuditFilterForm
from app.services.table_service import set_table_status, can_delete_table, can_delete_space
from app.services.finance_service import (
    create_manual_finance_entry,
    update_manual_finance_entry,
    delete_manual_finance_entry,
    get_finance_cashbook,
    get_dashboard_metrics
)
from app.services.audit_service import (
    get_audit_logs,
    export_audit_logs_csv
)
from app.services.export_service import (
    export_finance_csv,
    export_orders_csv
)
from app.utils.decorators import role_required
from app.utils.audit import log_audit

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
@login_required
@role_required('owner', 'manager')
def dashboard():
    """
    Management & Admin Dashboard.
    Accessible to Owners and Managers.
    - Owner sees comprehensive financial metrics (Sales, Paid, Unpaid, Expenses, Purchases, Net Profit),
      day-over-day delta comparisons, sales charts, and top selling dishes with revenue.
    - Manager sees an operational view (order counts, tables, top dishes by volume) without owner-only financial totals.
    """
    staff_count = User.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    category_count = Category.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    dish_count = Dish.query.filter_by(restaurant_id=current_user.restaurant_id, is_archived=False).count()
    space_count = Space.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    table_count = Table.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    occupied_count = Table.query.filter_by(restaurant_id=current_user.restaurant_id, status='occupied').count()

    metrics = get_dashboard_metrics(current_user.restaurant_id, current_user.role)

    return render_template(
        'admin/dashboard.html',
        staff_count=staff_count,
        category_count=category_count,
        dish_count=dish_count,
        space_count=space_count,
        table_count=table_count,
        occupied_count=occupied_count,
        metrics=metrics
    )

@admin_bp.route('/owner-only')
@login_required
@role_required('owner')
def owner_only_settings():
    """
    Sensitive financial/tax configuration area.
    Restricted strictly to the 'owner' role.
    Opening this as a 'manager' immediately yields HTTP 403 Forbidden.
    """
    return render_template('admin/owner_only.html')

# ==============================================================================
# MENU CATEGORIES CRUD (OWNER & MANAGER)
# ==============================================================================

@admin_bp.route('/categories')
@login_required
@role_required('owner', 'manager')
def category_list():
    """Directory listing of menu categories with dish counters and sort ordering."""
    categories = Category.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Category.sort_order.asc(), Category.name.asc()).all()

    dish_counts = {
        cat.id: Dish.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            category_id=cat.id,
            is_archived=False
        ).count()
        for cat in categories
    }

    return render_template(
        'admin/menu/categories.html',
        categories=categories,
        dish_counts=dish_counts
    )

@admin_bp.route('/categories/new', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def category_create():
    """Create a new menu category for the restaurant tenant."""
    form = CategoryForm()

    if form.validate_on_submit():
        name = form.name.data.strip()

        existing = Category.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            name=name
        ).first()

        if existing:
            flash(f"A category named '{name}' already exists in your restaurant.", "danger")
            return render_template('admin/menu/category_form.html', form=form, title="Create Category")

        category = Category(
            restaurant_id=current_user.restaurant_id,
            name=name,
            sort_order=form.sort_order.data or 0
        )
        db.session.add(category)
        db.session.commit()

        log_audit(
            action='CATEGORY_CREATED',
            record_type='Category',
            record_id=category.id,
            details={'name': category.name, 'sort_order': category.sort_order},
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Category '{category.name}' created successfully.", "success")
        return redirect(url_for('admin.category_list'))

    return render_template('admin/menu/category_form.html', form=form, title="Create Category")

@admin_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def category_edit(category_id):
    """Edit an existing menu category."""
    category = Category.query.filter_by(
        id=category_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    form = CategoryForm(obj=category)

    if form.validate_on_submit():
        new_name = form.name.data.strip()

        if new_name != category.name:
            existing = Category.query.filter(
                Category.restaurant_id == current_user.restaurant_id,
                Category.name == new_name,
                Category.id != category.id
            ).first()
            if existing:
                flash(f"A category named '{new_name}' already exists.", "danger")
                return render_template('admin/menu/category_form.html', form=form, category=category, title=f"Edit Category: {category.name}")

        old_name = category.name
        old_sort = category.sort_order

        category.name = new_name
        category.sort_order = form.sort_order.data or 0
        db.session.commit()

        log_audit(
            action='CATEGORY_UPDATED',
            record_type='Category',
            record_id=category.id,
            details={
                'old': {'name': old_name, 'sort_order': old_sort},
                'new': {'name': category.name, 'sort_order': category.sort_order}
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Category '{category.name}' updated successfully.", "success")
        return redirect(url_for('admin.category_list'))

    return render_template('admin/menu/category_form.html', form=form, category=category, title=f"Edit Category: {category.name}")

@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def category_delete(category_id):
    """Delete a menu category if all active dishes have been emptied or archived."""
    category = Category.query.filter_by(
        id=category_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    active_dish_count = Dish.query.filter_by(
        restaurant_id=current_user.restaurant_id,
        category_id=category.id,
        is_archived=False
    ).count()

    if active_dish_count > 0:
        flash(
            f"Cannot delete category '{category.name}' because it contains {active_dish_count} active dish(es). "
            f"Please reassign, empty, or archive its dishes first.",
            "danger"
        )
        return redirect(url_for('admin.category_list'))

    Dish.query.filter_by(
        restaurant_id=current_user.restaurant_id,
        category_id=category.id
    ).update({Dish.category_id: None})

    cat_name = category.name
    cat_id = category.id

    db.session.delete(category)
    db.session.commit()

    log_audit(
        action='CATEGORY_DELETED',
        record_type='Category',
        record_id=cat_id,
        details={'name': cat_name},
        user_id=current_user.id,
        restaurant_id=current_user.restaurant_id
    )

    flash(f"Category '{cat_name}' deleted successfully.", "success")
    return redirect(url_for('admin.category_list'))

# ==============================================================================
# DISHES CRUD & MENU MANAGEMENT (OWNER & MANAGER)
# ==============================================================================

@admin_bp.route('/dishes')
@login_required
@role_required('owner', 'manager')
def dish_list():
    """Directory listing of dishes with search, category filtering, and pagination."""
    search_query = request.args.get('q', '').strip()
    selected_cat_id = request.args.get('category_id', type=int)
    show_archived = request.args.get('archived', '0') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = 10

    query = Dish.query.filter(Dish.restaurant_id == current_user.restaurant_id)

    if not show_archived:
        query = query.filter(Dish.is_archived.is_(False))
    else:
        query = query.filter(Dish.is_archived.is_(True))

    if selected_cat_id:
        query = query.filter(Dish.category_id == selected_cat_id)

    if search_query:
        term = f"%{search_query}%"
        query = query.filter(Dish.name.ilike(term))

    pagination = query.order_by(
        Dish.category_id.asc(),
        Dish.name.asc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    categories = Category.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Category.name.asc()).all()

    return render_template(
        'admin/menu/dishes.html',
        pagination=pagination,
        dishes=pagination.items,
        categories=categories,
        selected_cat_id=selected_cat_id,
        search_query=search_query,
        show_archived=show_archived
    )

@admin_bp.route('/dishes/new', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def dish_create():
    """Create a new dish for the restaurant."""
    categories = Category.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Category.sort_order.asc(), Category.name.asc()).all()

    if not categories:
        flash("Please create at least one category before adding dishes to your menu.", "warning")
        return redirect(url_for('admin.category_create'))

    form = DishForm()
    form.category_id.choices = [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        dish = Dish(
            restaurant_id=current_user.restaurant_id,
            name=form.name.data.strip(),
            category_id=form.category_id.data,
            price=form.price.data,
            discount=form.discount.data or 0.00,
            veg_type=form.veg_type.data,
            prep_time_minutes=form.prep_time_minutes.data,
            is_available=form.is_available.data,
            is_archived=False
        )

        db.session.add(dish)
        db.session.commit()

        log_audit(
            action='DISH_CREATED',
            record_type='Dish',
            record_id=dish.id,
            details={
                'name': dish.name,
                'category_id': dish.category_id,
                'price': float(dish.price),
                'discount': float(dish.discount),
                'veg_type': dish.veg_type,
                'prep_time_minutes': dish.prep_time_minutes
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Dish '{dish.name}' added to menu successfully.", "success")
        return redirect(url_for('admin.dish_list'))

    return render_template('admin/menu/dish_form.html', form=form, title="Add New Dish")

@admin_bp.route('/dishes/<int:dish_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def dish_edit(dish_id):
    """Edit dish details, price, discount, and availability."""
    dish = Dish.query.filter_by(
        id=dish_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    categories = Category.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Category.sort_order.asc(), Category.name.asc()).all()

    form = DishForm(obj=dish)
    form.category_id.choices = [(c.id, c.name) for c in categories]

    if form.validate_on_submit():
        old_price = dish.price
        old_discount = dish.discount

        dish.name = form.name.data.strip()
        dish.category_id = form.category_id.data
        dish.price = form.price.data
        dish.discount = form.discount.data or 0.00
        dish.veg_type = form.veg_type.data
        dish.prep_time_minutes = form.prep_time_minutes.data
        dish.is_available = form.is_available.data

        db.session.commit()

        price_modified = (old_price != dish.price) or (old_discount != dish.discount)
        if price_modified:
            log_audit(
                action='DISH_PRICE_CHANGED',
                record_type='Dish',
                record_id=dish.id,
                details={
                    'dish_name': dish.name,
                    'old_price': float(old_price),
                    'new_price': float(dish.price),
                    'old_discount': float(old_discount),
                    'new_discount': float(dish.discount)
                },
                user_id=current_user.id,
                restaurant_id=current_user.restaurant_id
            )
        else:
            log_audit(
                action='DISH_UPDATED',
                record_type='Dish',
                record_id=dish.id,
                details={'name': dish.name, 'category_id': dish.category_id},
                user_id=current_user.id,
                restaurant_id=current_user.restaurant_id
            )

        flash(f"Dish '{dish.name}' updated successfully.", "success")
        return redirect(url_for('admin.dish_list'))

    return render_template('admin/menu/dish_form.html', form=form, dish=dish, title=f"Edit Dish: {dish.name}")

@admin_bp.route('/dishes/<int:dish_id>/toggle-available', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def dish_toggle_available(dish_id):
    """Instant HTMX availability toggle for dishes."""
    dish = Dish.query.filter_by(
        id=dish_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    dish.is_available = not dish.is_available
    db.session.commit()

    log_audit(
        action='DISH_AVAILABILITY_TOGGLED',
        record_type='Dish',
        record_id=dish.id,
        details={'name': dish.name, 'is_available': dish.is_available},
        user_id=current_user.id,
        restaurant_id=current_user.restaurant_id
    )

    if request.headers.get('HX-Request'):
        return render_template('admin/menu/_dish_availability_cell.html', dish=dish)

    status_str = "available" if dish.is_available else "marked unavailable"
    flash(f"Dish '{dish.name}' is now {status_str}.", "success")
    return redirect(url_for('admin.dish_list'))

@admin_bp.route('/dishes/<int:dish_id>/delete', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def dish_delete(dish_id):
    """Delete or soft-archive a dish depending on historical order references."""
    dish = Dish.query.filter_by(
        id=dish_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    order_item_exists = OrderItem.query.filter_by(dish_id=dish.id).first() is not None

    if order_item_exists:
        dish.is_archived = True
        dish.is_available = False
        db.session.commit()

        log_audit(
            action='DISH_ARCHIVED',
            record_type='Dish',
            record_id=dish.id,
            details={
                'name': dish.name,
                'reason': 'Archived to preserve historical customer orders'
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(
            f"Dish '{dish.name}' has been ordered previously, so it cannot be hard-deleted. "
            f"It has been archived and hidden from the POS.",
            "info"
        )
    else:
        dish_name = dish.name
        dish_id_val = dish.id

        db.session.delete(dish)
        db.session.commit()

        log_audit(
            action='DISH_DELETED',
            record_type='Dish',
            record_id=dish_id_val,
            details={'name': dish_name},
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Dish '{dish_name}' deleted permanently from the menu.", "success")

    return redirect(url_for('admin.dish_list'))

# ==============================================================================
# DINING SPACES CRUD (OWNER & MANAGER)
# ==============================================================================

@admin_bp.route('/spaces')
@login_required
@role_required('owner', 'manager')
def space_list():
    """List all dining spaces with table count breakdowns."""
    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    space_stats = {}
    for sp in spaces:
        total = Table.query.filter_by(restaurant_id=current_user.restaurant_id, space_id=sp.id).count()
        occupied = Table.query.filter_by(restaurant_id=current_user.restaurant_id, space_id=sp.id, status='occupied').count()
        space_stats[sp.id] = {
            'total': total,
            'open': total - occupied,
            'occupied': occupied
        }

    return render_template(
        'admin/spaces/index.html',
        spaces=spaces,
        space_stats=space_stats
    )

@admin_bp.route('/spaces/new', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def space_create():
    """Create a new dining space / zone."""
    form = SpaceForm()

    if form.validate_on_submit():
        name = form.name.data.strip()

        existing = Space.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            name=name
        ).first()

        if existing:
            flash(f"A space named '{name}' already exists in your restaurant.", "danger")
            return render_template('admin/spaces/form.html', form=form, title="Create Dining Space")

        space = Space(
            restaurant_id=current_user.restaurant_id,
            name=name
        )
        db.session.add(space)
        db.session.commit()

        log_audit(
            action='SPACE_CREATED',
            record_type='Space',
            record_id=space.id,
            details={'name': space.name},
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Dining space '{space.name}' created successfully.", "success")
        return redirect(url_for('admin.space_list'))

    return render_template('admin/spaces/form.html', form=form, title="Create Dining Space")

@admin_bp.route('/spaces/<int:space_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def space_edit(space_id):
    """Edit an existing dining space."""
    space = Space.query.filter_by(
        id=space_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    form = SpaceForm(obj=space)

    if form.validate_on_submit():
        new_name = form.name.data.strip()

        if new_name != space.name:
            existing = Space.query.filter(
                Space.restaurant_id == current_user.restaurant_id,
                Space.name == new_name,
                Space.id != space.id
            ).first()
            if existing:
                flash(f"A space named '{new_name}' already exists.", "danger")
                return render_template('admin/spaces/form.html', form=form, space=space, title=f"Edit Space: {space.name}")

        old_name = space.name
        space.name = new_name
        db.session.commit()

        log_audit(
            action='SPACE_UPDATED',
            record_type='Space',
            record_id=space.id,
            details={'old_name': old_name, 'new_name': space.name},
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Dining space '{space.name}' updated successfully.", "success")
        return redirect(url_for('admin.space_list'))

    return render_template('admin/spaces/form.html', form=form, space=space, title=f"Edit Space: {space.name}")

@admin_bp.route('/spaces/<int:space_id>/delete', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def space_delete(space_id):
    """Delete a dining space if none of its tables are currently occupied or hold open orders."""
    space = Space.query.filter_by(
        id=space_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    can_delete, reason = can_delete_space(space.id, current_user.restaurant_id)
    if not can_delete:
        flash(reason, "danger")
        return redirect(url_for('admin.space_list'))

    space_name = space.name
    space_id_val = space.id

    db.session.delete(space)
    db.session.commit()

    log_audit(
        action='SPACE_DELETED',
        record_type='Space',
        record_id=space_id_val,
        details={'name': space_name},
        user_id=current_user.id,
        restaurant_id=current_user.restaurant_id
    )

    flash(f"Dining space '{space_name}' and its tables deleted successfully.", "success")
    return redirect(url_for('admin.space_list'))

# ==============================================================================
# TABLES CRUD & LIVE STATUS BOARD (OWNER, MANAGER, CASHIER)
# ==============================================================================

@admin_bp.route('/tables')
@login_required
@role_required('owner', 'manager')
def table_list():
    """Management listing of all dining tables with search and space filter."""
    selected_space_id = request.args.get('space_id', type=int)
    search_query = request.args.get('q', '').strip()

    query = Table.query.filter(Table.restaurant_id == current_user.restaurant_id)

    if selected_space_id:
        query = query.filter(Table.space_id == selected_space_id)

    if search_query:
        term = f"%{search_query}%"
        query = query.filter(Table.name.ilike(term))

    tables = query.order_by(Table.space_id.asc(), Table.name.asc()).all()
    spaces = Space.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(Space.name.asc()).all()

    return render_template(
        'admin/tables/index.html',
        tables=tables,
        spaces=spaces,
        selected_space_id=selected_space_id,
        search_query=search_query
    )

@admin_bp.route('/tables/board')
@login_required
@role_required('owner', 'manager', 'cashier')
def table_board():
    """
    Live Visual Table Status Board.
    Accessible to Owners, Managers, and Cashiers.
    Auto-refreshes periodically using HTMX polling to reflect live dining status.
    """
    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    total_tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    occupied_tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id, status='occupied').count()
    open_tables = total_tables - occupied_tables

    return render_template(
        'admin/tables/board.html',
        spaces=spaces,
        total_tables=total_tables,
        open_tables=open_tables,
        occupied_tables=occupied_tables
    )

@admin_bp.route('/tables/board/partial')
@login_required
@role_required('owner', 'manager', 'cashier')
def table_board_partial():
    """HTMX polling endpoint returning updated live table cards grouped by space."""
    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    total_tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id).count()
    occupied_tables = Table.query.filter_by(restaurant_id=current_user.restaurant_id, status='occupied').count()
    open_tables = total_tables - occupied_tables

    return render_template(
        'admin/tables/_board_grid.html',
        spaces=spaces,
        total_tables=total_tables,
        open_tables=open_tables,
        occupied_tables=occupied_tables
    )

@admin_bp.route('/tables/new', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def table_create():
    """Create an individual dining table."""
    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    if not spaces:
        flash("Please create at least one dining space before adding tables.", "warning")
        return redirect(url_for('admin.space_create'))

    form = TableForm()
    form.space_id.choices = [(s.id, s.name) for s in spaces]

    if form.validate_on_submit():
        name = form.name.data.strip()

        existing = Table.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            space_id=form.space_id.data,
            name=name
        ).first()

        if existing:
            flash(f"A table named '{name}' already exists in this space.", "danger")
            return render_template('admin/tables/form.html', form=form, title="Add Dining Table")

        table = Table(
            restaurant_id=current_user.restaurant_id,
            space_id=form.space_id.data,
            name=name,
            capacity=form.capacity.data,
            cover_charge=form.cover_charge.data or 0.00,
            status=form.status.data
        )

        db.session.add(table)
        db.session.commit()

        log_audit(
            action='TABLE_CREATED',
            record_type='Table',
            record_id=table.id,
            details={
                'name': table.name,
                'space_id': table.space_id,
                'capacity': table.capacity,
                'cover_charge': float(table.cover_charge)
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Table '{table.name}' created successfully.", "success")
        return redirect(url_for('admin.table_list'))

    return render_template('admin/tables/form.html', form=form, title="Add Dining Table")

@admin_bp.route('/tables/bulk', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def table_bulk_create():
    """
    Bulk table generator: creates a batch of tables (e.g. T1 through T20).
    Saves significant manual setup time during restaurant onboarding.
    """
    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    if not spaces:
        flash("Please create at least one dining space before generating tables.", "warning")
        return redirect(url_for('admin.space_create'))

    form = BulkTableForm()
    form.space_id.choices = [(s.id, s.name) for s in spaces]

    if form.validate_on_submit():
        space_id = form.space_id.data
        prefix = form.prefix.data.strip()
        from_num = form.from_number.data
        to_num = form.to_number.data
        capacity = form.capacity.data
        cover_charge = form.cover_charge.data or 0.00

        created_names = []
        skipped_names = []

        for num in range(from_num, to_num + 1):
            table_name = f"{prefix}{num}"

            existing = Table.query.filter_by(
                restaurant_id=current_user.restaurant_id,
                space_id=space_id,
                name=table_name
            ).first()

            if existing:
                skipped_names.append(table_name)
                continue

            tbl = Table(
                restaurant_id=current_user.restaurant_id,
                space_id=space_id,
                name=table_name,
                capacity=capacity,
                cover_charge=cover_charge,
                status='open'
            )
            db.session.add(tbl)
            created_names.append(table_name)

        db.session.commit()

        if created_names:
            log_audit(
                action='TABLES_BULK_CREATED',
                record_type='Table',
                record_id=space_id,
                details={
                    'space_id': space_id,
                    'created_count': len(created_names),
                    'range': f"{created_names[0]} - {created_names[-1]}",
                    'capacity': capacity
                },
                user_id=current_user.id,
                restaurant_id=current_user.restaurant_id
            )

        msg = f"Successfully generated {len(created_names)} tables ({prefix}{from_num} through {prefix}{to_num})."
        if skipped_names:
            msg += f" Note: {len(skipped_names)} table(s) already existed and were skipped ({', '.join(skipped_names[:5])})."

        flash(msg, "success" if created_names else "warning")
        return redirect(url_for('admin.table_list'))

    return render_template('admin/tables/bulk_form.html', form=form, title="Bulk Generate Tables")

@admin_bp.route('/tables/<int:table_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def table_edit(table_id):
    """Edit table parameters: name, space, capacity, cover charge, status."""
    table = Table.query.filter_by(
        id=table_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    spaces = Space.query.filter_by(
        restaurant_id=current_user.restaurant_id
    ).order_by(Space.name.asc()).all()

    form = TableForm(obj=table)
    form.space_id.choices = [(s.id, s.name) for s in spaces]

    if form.validate_on_submit():
        new_name = form.name.data.strip()

        if new_name != table.name or form.space_id.data != table.space_id:
            existing = Table.query.filter(
                Table.restaurant_id == current_user.restaurant_id,
                Table.space_id == form.space_id.data,
                Table.name == new_name,
                Table.id != table.id
            ).first()
            if existing:
                flash(f"A table named '{new_name}' already exists in that space.", "danger")
                return render_template('admin/tables/form.html', form=form, table=table, title=f"Edit Table: {table.name}")

        old_data = {
            'name': table.name,
            'space_id': table.space_id,
            'capacity': table.capacity,
            'cover_charge': float(table.cover_charge),
            'status': table.status
        }

        table.space_id = form.space_id.data
        table.name = new_name
        table.capacity = form.capacity.data
        table.cover_charge = form.cover_charge.data or 0.00
        table.status = form.status.data

        db.session.commit()

        log_audit(
            action='TABLE_UPDATED',
            record_type='Table',
            record_id=table.id,
            details={
                'old': old_data,
                'new': {
                    'name': table.name,
                    'space_id': table.space_id,
                    'capacity': table.capacity,
                    'cover_charge': float(table.cover_charge),
                    'status': table.status
                }
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Table '{table.name}' updated successfully.", "success")
        return redirect(url_for('admin.table_list'))

    return render_template('admin/tables/form.html', form=form, table=table, title=f"Edit Table: {table.name}")

@admin_bp.route('/tables/<int:table_id>/delete', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def table_delete(table_id):
    """
    Delete a dining table.
    Safety rule: Prevent deleting a table that has open orders or is currently marked occupied.
    """
    table = Table.query.filter_by(
        id=table_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    can_delete, reason = can_delete_table(table.id, current_user.restaurant_id)
    if not can_delete:
        flash(reason, "danger")
        return redirect(url_for('admin.table_list'))

    table_name = table.name
    table_id_val = table.id

    db.session.delete(table)
    db.session.commit()

    log_audit(
        action='TABLE_DELETED',
        record_type='Table',
        record_id=table_id_val,
        details={'name': table_name},
        user_id=current_user.id,
        restaurant_id=current_user.restaurant_id
    )

    flash(f"Table '{table_name}' deleted successfully.", "success")
    return redirect(url_for('admin.table_list'))

@admin_bp.route('/tables/<int:table_id>/toggle-status', methods=['POST'])
@login_required
@role_required('owner', 'manager', 'cashier')
def table_toggle_status(table_id):
    """
    Quick status toggle for a dining table between 'open' and 'occupied'.
    Uses the reusable set_table_status() service function.
    """
    table = Table.query.filter_by(
        id=table_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    target_status = 'occupied' if table.status == 'open' else 'open'
    set_table_status(
        table_id=table.id,
        status=target_status,
        restaurant_id=current_user.restaurant_id,
        user_id=current_user.id
    )

    if request.headers.get('HX-Request'):
        return render_template('admin/tables/_table_status_card.html', table=table)

    flash(f"Table '{table.name}' status changed to {target_status.upper()}.", "success")
    return redirect(request.referrer or url_for('admin.table_board'))

# ==============================================================================
# RESTAURANT PROFILE & TAX SETTINGS (OWNER-ONLY)
# ==============================================================================

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('owner')
def settings():
    """
    Restaurant profile, BIN, VAT rate, price mode, and receipt footer configuration.
    Strictly Owner-only on the server.
    Changes apply strictly to NEW orders; historical order snapshots remain immutable.
    """
    restaurant = current_user.restaurant
    form = RestaurantSettingsForm(obj=restaurant)

    if form.validate_on_submit():
        old_data = {
            'name': restaurant.name,
            'phone': restaurant.phone,
            'address': restaurant.address,
            'bin': restaurant.bin,
            'vat_rate': float(restaurant.vat_rate),
            'price_mode': restaurant.price_mode,
            'receipt_footer': restaurant.receipt_footer
        }

        restaurant.name = form.name.data.strip()
        restaurant.phone = form.phone.data.strip()
        restaurant.address = form.address.data.strip() if form.address.data else None
        restaurant.bin = form.bin.data.strip() if form.bin.data else None
        restaurant.vat_rate = form.vat_rate.data
        restaurant.price_mode = form.price_mode.data
        restaurant.receipt_footer = form.receipt_footer.data.strip() if form.receipt_footer.data else None

        db.session.commit()

        new_data = {
            'name': restaurant.name,
            'phone': restaurant.phone,
            'address': restaurant.address,
            'bin': restaurant.bin,
            'vat_rate': float(restaurant.vat_rate),
            'price_mode': restaurant.price_mode,
            'receipt_footer': restaurant.receipt_footer
        }

        log_audit(
            action='SETTINGS_UPDATED',
            record_type='Restaurant',
            record_id=restaurant.id,
            details={'old': old_data, 'new': new_data},
            user_id=current_user.id,
            restaurant_id=restaurant.id
        )

        flash("Restaurant settings and VAT parameters updated successfully. These will apply to all new orders.", "success")
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', form=form, restaurant=restaurant)

# ==============================================================================
# STAFF MANAGEMENT CRUD (OWNER-ONLY)
# ==============================================================================

@admin_bp.route('/staff')
@login_required
@role_required('owner')
def staff_list():
    """Directory listing of staff members for the current restaurant tenant with search & pagination."""
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10

    query = User.query.filter(User.restaurant_id == current_user.restaurant_id)

    if search_query:
        term = f"%{search_query}%"
        query = query.filter(
            db.or_(
                User.name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term)
            )
        )

    pagination = query.order_by(User.role.asc(), User.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        'admin/staff/index.html',
        pagination=pagination,
        staff_members=pagination.items,
        search_query=search_query
    )

@admin_bp.route('/staff/new', methods=['GET', 'POST'])
@login_required
@role_required('owner')
def staff_create():
    """Create a new staff member account under this restaurant tenant."""
    form = StaffCreateForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        existing_user = User.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            email=email
        ).first()

        if existing_user:
            flash("A staff member with this email already exists in your restaurant.", "danger")
            return render_template('admin/staff/form.html', form=form, title="Add Staff Member")

        new_user = User(
            restaurant_id=current_user.restaurant_id,
            name=form.name.data.strip(),
            email=email,
            phone=form.phone.data.strip() if form.phone.data else None,
            role=form.role.data,
            is_active=True
        )
        new_user.set_password(form.password.data)

        db.session.add(new_user)
        db.session.commit()

        log_audit(
            action='STAFF_CREATED',
            record_type='User',
            record_id=new_user.id,
            details={
                'name': new_user.name,
                'email': new_user.email,
                'role': new_user.role,
                'phone': new_user.phone
            },
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Staff member '{new_user.name}' ({new_user.role.title()}) created successfully.", "success")
        return redirect(url_for('admin.staff_list'))

    return render_template('admin/staff/form.html', form=form, title="Add Staff Member")

@admin_bp.route('/staff/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner')
def staff_edit(user_id):
    """Edit staff details and permissions."""
    user = User.query.filter_by(
        id=user_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    form = StaffEditForm(obj=user)

    if form.validate_on_submit():
        new_email = form.email.data.strip().lower()

        if new_email != user.email:
            existing = User.query.filter(
                User.restaurant_id == current_user.restaurant_id,
                User.email == new_email,
                User.id != user.id
            ).first()
            if existing:
                flash("Another staff member with this email already exists.", "danger")
                return render_template('admin/staff/form.html', form=form, staff=user, title=f"Edit {user.name}")

        active_owners_count = User.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            role='owner',
            is_active=True
        ).count()

        if user.role == 'owner' and user.is_active and active_owners_count <= 1:
            if form.role.data != 'owner':
                flash("Cannot demote the last active owner of the restaurant.", "danger")
                return render_template('admin/staff/form.html', form=form, staff=user, title=f"Edit {user.name}")
            if not form.is_active.data:
                flash("Cannot deactivate the last active owner of the restaurant.", "danger")
                return render_template('admin/staff/form.html', form=form, staff=user, title=f"Edit {user.name}")

        old_data = {
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'is_active': user.is_active
        }

        user.name = form.name.data.strip()
        user.email = new_email
        user.phone = form.phone.data.strip() if form.phone.data else None
        user.role = form.role.data
        user.is_active = form.is_active.data

        password_changed = False
        if form.password.data and form.password.data.strip():
            user.set_password(form.password.data.strip())
            user.failed_login_count = 0
            user.locked_until = None
            password_changed = True

        db.session.commit()

        new_data = {
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'role': user.role,
            'is_active': user.is_active,
            'password_changed': password_changed
        }

        log_audit(
            action='STAFF_UPDATED',
            record_type='User',
            record_id=user.id,
            details={'old': old_data, 'new': new_data},
            user_id=current_user.id,
            restaurant_id=current_user.restaurant_id
        )

        flash(f"Staff member '{user.name}' updated successfully.", "success")
        return redirect(url_for('admin.staff_list'))

    return render_template('admin/staff/form.html', form=form, staff=user, title=f"Edit Staff: {user.name}")

@admin_bp.route('/staff/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@role_required('owner')
def staff_toggle_status(user_id):
    """Toggle staff account between Active and Inactive."""
    user = User.query.filter_by(
        id=user_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    if user.role == 'owner' and user.is_active:
        active_owners_count = User.query.filter_by(
            restaurant_id=current_user.restaurant_id,
            role='owner',
            is_active=True
        ).count()
        if active_owners_count <= 1:
            error_msg = "Cannot deactivate the last active owner of the restaurant."
            if request.headers.get('HX-Request'):
                return render_template('admin/staff/_status_cell.html', staff=user, error=error_msg), 400
            flash(error_msg, "danger")
            return redirect(url_for('admin.staff_list'))

    old_status = user.is_active
    user.is_active = not user.is_active
    db.session.commit()

    log_audit(
        action='STAFF_STATUS_TOGGLED',
        record_type='User',
        record_id=user.id,
        details={'old_active': old_status, 'new_active': user.is_active},
        user_id=current_user.id,
        restaurant_id=current_user.restaurant_id
    )

    if request.headers.get('HX-Request'):
        return render_template('admin/staff/_status_cell.html', staff=user)

    action_text = "activated" if user.is_active else "deactivated"
    flash(f"Staff member '{user.name}' has been {action_text}.", "success")
    return redirect(url_for('admin.staff_list'))

# ==============================================================================
# FINANCIAL CASHBOOK & EXPENSES (OWNER & MANAGER)
# ==============================================================================

@admin_bp.route('/finance')
@login_required
@role_required('owner', 'manager')
def finance_list():
    """
    Cashbook ledger directory with type and date range filters, pagination,
    and daily/monthly aggregate balance totals.
    Read-only protection for automated POS order sales entries.
    """
    page = request.args.get('page', 1, type=int)
    entry_type = request.args.get('type', 'all')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    filter_form = FinanceFilterForm(request.args)
    if start_date:
        filter_form.start_date.data = start_date
    if end_date:
        filter_form.end_date.data = end_date
    if entry_type:
        filter_form.type.data = entry_type

    cashbook_data = get_finance_cashbook(
        restaurant_id=current_user.restaurant_id,
        entry_type=entry_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=15
    )

    return render_template(
        'admin/finance/index.html',
        filter_form=filter_form,
        pagination=cashbook_data['pagination'],
        entries=cashbook_data['entries'],
        daily_totals=cashbook_data['daily_totals'],
        monthly_totals=cashbook_data['monthly_totals'],
        current_type=entry_type,
        current_start_date=start_date_str,
        current_end_date=end_date_str
    )

@admin_bp.route('/finance/new', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def finance_create():
    """Create a new manual finance cashbook entry (market purchase, expense, or manual sale)."""
    form = FinanceEntryForm()

    if form.validate_on_submit():
        try:
            entry = create_manual_finance_entry(
                restaurant_id=current_user.restaurant_id,
                user_id=current_user.id,
                entry_type=form.type.data,
                amount=form.amount.data,
                note=form.note.data,
                entry_date=form.entry_date.data
            )
            flash(f"Finance entry recorded: {entry.type.title()} ৳{entry.amount:,.2f}", "success")
            return redirect(url_for('admin.finance_list'))
        except ValueError as e:
            flash(str(e), "danger")

    return render_template('admin/finance/form.html', form=form, mode='create')

@admin_bp.route('/finance/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('owner', 'manager')
def finance_edit(entry_id):
    """
    Edit a manual finance entry.
    INVARIANT: Automated POS sales entries (order_id is not None) are strictly read-only.
    """
    entry = FinanceEntry.query.filter_by(
        id=entry_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    if entry.order_id is not None:
        flash("Entries automatically generated from POS orders are read-only and cannot be modified.", "danger")
        return redirect(url_for('admin.finance_list'))

    form = FinanceEntryForm()
    if request.method == 'GET':
        form.type.data = entry.type
        form.amount.data = entry.amount
        form.entry_date.data = entry.entry_date.date() if entry.entry_date else date.today()
        form.note.data = entry.note

    if form.validate_on_submit():
        try:
            update_manual_finance_entry(
                entry_id=entry.id,
                restaurant_id=current_user.restaurant_id,
                user_id=current_user.id,
                entry_type=form.type.data,
                amount=form.amount.data,
                note=form.note.data,
                entry_date=form.entry_date.data
            )
            flash(f"Finance entry #{entry.id} updated successfully.", "success")
            return redirect(url_for('admin.finance_list'))
        except (ValueError, PermissionError) as e:
            flash(str(e), "danger")

    return render_template('admin/finance/form.html', form=form, mode='edit', entry=entry)

@admin_bp.route('/finance/<int:entry_id>/delete', methods=['POST'])
@login_required
@role_required('owner', 'manager')
def finance_delete(entry_id):
    """
    Delete a manual finance entry.
    INVARIANT: Automated POS sales entries (order_id is not None) are strictly read-only.
    """
    entry = FinanceEntry.query.filter_by(
        id=entry_id,
        restaurant_id=current_user.restaurant_id
    ).first_or_404()

    if entry.order_id is not None:
        flash("Entries automatically generated from POS orders are read-only and cannot be deleted.", "danger")
        return redirect(url_for('admin.finance_list'))

    try:
        delete_manual_finance_entry(
            entry_id=entry.id,
            restaurant_id=current_user.restaurant_id,
            user_id=current_user.id
        )
        flash(f"Finance entry #{entry.id} deleted successfully.", "success")
    except (ValueError, PermissionError) as e:
        flash(str(e), "danger")

    return redirect(url_for('admin.finance_list'))

# ==============================================================================
# AUDIT LOG & COMPLIANCE (OWNER FULL, MANAGER VIEW-ONLY)
# ==============================================================================

@admin_bp.route('/audit')
@login_required
@role_required('owner', 'manager')
def audit_list():
    """
    Compliance Audit Trail viewer.
    - Owner: Full access (filtering, inspection, CSV export).
    - Manager: View-only access (can view and filter; no administrative export).
    - Non-negotiable Rule 5 & Immutability: Audit records CANNOT be edited or deleted through the app.
    """
    page = request.args.get('page', 1, type=int)
    user_id_param = request.args.get('user_id', '')
    action_param = request.args.get('action', '')
    record_type_param = request.args.get('record_type', '')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    # Populate staff choices for dropdown
    staff_members = User.query.filter_by(restaurant_id=current_user.restaurant_id).order_by(User.name.asc()).all()
    user_choices = [('', 'All Staff Members')] + [(str(u.id), f"{u.name} ({u.role.title()})") for u in staff_members]

    filter_form = AuditFilterForm(request.args)
    filter_form.user_id.choices = user_choices
    if user_id_param:
        filter_form.user_id.data = user_id_param
    if action_param:
        filter_form.action.data = action_param
    if record_type_param:
        filter_form.record_type.data = record_type_param
    if start_date:
        filter_form.start_date.data = start_date
    if end_date:
        filter_form.end_date.data = end_date

    user_id_int = int(user_id_param) if user_id_param and user_id_param.isdigit() else None

    pagination = get_audit_logs(
        restaurant_id=current_user.restaurant_id,
        user_id=user_id_int,
        action=action_param,
        record_type=record_type_param,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=25
    )

    return render_template(
        'admin/audit/index.html',
        filter_form=filter_form,
        pagination=pagination,
        logs=pagination.items,
        current_user_id=user_id_param,
        current_action=action_param,
        current_record_type=record_type_param,
        current_start_date=start_date_str,
        current_end_date=end_date_str,
        is_owner=(current_user.role == 'owner')
    )

@admin_bp.route('/audit/export.csv')
@login_required
@role_required('owner')
def audit_export_csv():
    """CSV export of audit logs for off-server compliance archival (Owner only)."""
    user_id_param = request.args.get('user_id', '')
    action_param = request.args.get('action', '')
    record_type_param = request.args.get('record_type', '')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    user_id_int = int(user_id_param) if user_id_param and user_id_param.isdigit() else None

    csv_data = export_audit_logs_csv(
        restaurant_id=current_user.restaurant_id,
        user_id=user_id_int,
        action=action_param,
        record_type=record_type_param,
        start_date=start_date,
        end_date=end_date
    )

    filename = f"audit_log_{current_user.restaurant_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

# ==============================================================================
# CSV EXPORT ROUTES (OWNER & MANAGER)
# ==============================================================================

@admin_bp.route('/finance/export.csv')
@login_required
@role_required('owner', 'manager')
def finance_export_csv():
    """
    CSV export for financial cashbook entries.
    Exported totals match on-screen totals exactly.
    """
    entry_type = request.args.get('type', 'all')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    csv_data = export_finance_csv(
        restaurant_id=current_user.restaurant_id,
        entry_type=entry_type,
        start_date=start_date,
        end_date=end_date
    )

    filename = f"finance_cashbook_{current_user.restaurant_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@admin_bp.route('/orders/export.csv')
@login_required
@role_required('owner', 'manager')
def orders_export_csv():
    """
    CSV export for orders directory.
    Exported totals match on-screen totals exactly.
    """
    status = request.args.get('status', 'all')
    order_type = request.args.get('type', 'all')
    staff_id_str = request.args.get('staff', '')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    order_no_str = request.args.get('order_no', '').strip()

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = None

    staff_id = int(staff_id_str) if staff_id_str and staff_id_str.isdigit() else None
    order_no = int(order_no_str) if order_no_str and order_no_str.isdigit() else None

    csv_data = export_orders_csv(
        restaurant_id=current_user.restaurant_id,
        status=status,
        order_type=order_type,
        staff_id=staff_id,
        start_date=start_date,
        end_date=end_date,
        order_no=order_no
    )

    filename = f"orders_{current_user.restaurant_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
