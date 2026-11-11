import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import unittest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.finance import FinanceEntry
from app.models.audit import AuditLog
from app.services.billing_service import calculate_bill, record_order_payment
from app.services.order_service import create_pos_order
from app.services.finance_service import (
    create_manual_finance_entry,
    update_manual_finance_entry,
    delete_manual_finance_entry,
    get_finance_cashbook,
    get_dashboard_metrics
)

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-11'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class TestStep11FinanceAndDashboard(unittest.TestCase):
    """
    Test suite for Step 11: Basic Finance Cashbook & Analytics Dashboard.
    Verifies:
      1. Manual finance entries CRUD (sale, purchase, expense) with BDT exactness.
      2. Automated POS order sales entries are strictly READ-ONLY.
      3. Exact reconciliation between Orders, FinanceEntries, and Dashboard KPIs.
      4. Day-over-day comparison (Today vs Yesterday) calculations.
      5. Top 5 selling dishes ranking and revenue snapshots.
      6. Role-based dashboard perspectives (Owner full financial suite vs Manager operational view).
      7. Non-negotiable multi-tenant isolation and AuditLog recording.
    """

    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['WTF_CSRF_ENABLED'] = False  # Disabled for direct test client HTTP posts
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant A (Primary)
        self.rest_a = Restaurant(
            name="Sultan's Dine Dhanmondi",
            phone="01711111111",
            address="Dhanmondi 27, Dhaka",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        # Seed Restaurant B (Tenant Isolation verification)
        self.rest_b = Restaurant(
            name="Kacchi Bhai Gulshan",
            phone="01722222222",
            address="Gulshan 1, Dhaka",
            bin="987654321-0202",
            vat_rate=Decimal("10.00"),
            price_mode="inclusive"
        )
        db.session.add_all([self.rest_a, self.rest_b])
        db.session.commit()

        # Seed Users for Restaurant A
        self.owner_a = User(
            restaurant_id=self.rest_a.id,
            name="Owner A",
            email="owner@sultans.com",
            phone="01710000001",
            role="owner",
            is_active=True
        )
        self.owner_a.set_password("OwnerPass123!")

        self.manager_a = User(
            restaurant_id=self.rest_a.id,
            name="Manager A",
            email="manager@sultans.com",
            phone="01710000002",
            role="manager",
            is_active=True
        )
        self.manager_a.set_password("ManagerPass123!")

        self.cashier_a = User(
            restaurant_id=self.rest_a.id,
            name="Cashier A",
            email="cashier@sultans.com",
            phone="01710000003",
            role="cashier",
            is_active=True
        )
        self.cashier_a.set_password("CashierPass123!")

        # Seed Owner for Restaurant B
        self.owner_b = User(
            restaurant_id=self.rest_b.id,
            name="Owner B",
            email="owner@kacchibhai.com",
            phone="01720000001",
            role="owner",
            is_active=True
        )
        self.owner_b.set_password("OwnerBPass123!")

        db.session.add_all([self.owner_a, self.manager_a, self.cashier_a, self.owner_b])
        db.session.commit()

        # Seed Menu & Space for Restaurant A
        self.cat_a = Category(restaurant_id=self.rest_a.id, name="Biryani", sort_order=1)
        db.session.add(self.cat_a)
        db.session.commit()

        self.dish_kacchi = Dish(
            restaurant_id=self.rest_a.id,
            category_id=self.cat_a.id,
            name="Mutton Kacchi Basmati",
            price=Decimal("450.00"),
            veg_type="non-veg",
            is_available=True
        )
        self.dish_borhani = Dish(
            restaurant_id=self.rest_a.id,
            category_id=self.cat_a.id,
            name="Borhani 250ml",
            price=Decimal("80.00"),
            veg_type="veg",
            is_available=True
        )
        self.dish_kabab = Dish(
            restaurant_id=self.rest_a.id,
            category_id=self.cat_a.id,
            name="Jali Kabab",
            price=Decimal("70.00"),
            veg_type="non-veg",
            is_available=True
        )
        db.session.add_all([self.dish_kacchi, self.dish_borhani, self.dish_kabab])
        db.session.commit()

        self.space_a = Space(restaurant_id=self.rest_a.id, name="Main Hall")
        db.session.add(self.space_a)
        db.session.commit()

        self.table_a = Table(restaurant_id=self.rest_a.id, space_id=self.space_a.id, name="T-01", capacity=4)
        db.session.add(self.table_a)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_user(self, user):
        """Helper to authenticate a user via the login route."""
        self.client.get('/auth/logout')
        return self.client.post('/auth/login', data={
            'identifier': user.email,
            'password': 'OwnerPass123!' if user.role == 'owner' and user.id == self.owner_a.id else (
                'ManagerPass123!' if user.role == 'manager' else (
                    'CashierPass123!' if user.role == 'cashier' else 'OwnerBPass123!'
                )
            )
        }, follow_redirects=True)

    # ==========================================================================
    # 1. MANUAL FINANCE ENTRIES CRUD & AUDIT LOGGING
    # ==========================================================================

    def test_manual_finance_entry_create_service(self):
        """Creates manual purchase, expense, and sale entries with exact BDT decimal values."""
        entry = create_manual_finance_entry(
            restaurant_id=self.rest_a.id,
            user_id=self.owner_a.id,
            entry_type='purchase',
            amount=Decimal('1250.50'),
            note='50kg Basmati Rice from Badamtali',
            entry_date=date.today()
        )

        assert entry.id is not None
        assert entry.restaurant_id == self.rest_a.id
        assert entry.type == 'purchase'
        assert entry.amount == Decimal('1250.50')
        assert entry.order_id is None
        assert entry.created_by == self.owner_a.id

        # Verify AuditLog entry was written
        audit = AuditLog.query.filter_by(
            restaurant_id=self.rest_a.id,
            action='FINANCE_ENTRY_CREATED',
            record_id=entry.id
        ).first()
        assert audit is not None
        assert audit.details['type'] == 'purchase'
        assert audit.details['amount'] == '1250.50'

    def test_manual_finance_entry_negative_amount_rejected(self):
        """Rejects zero or negative amounts with ValueError."""
        with pytest.raises(ValueError, match="Amount must be greater than zero"):
            create_manual_finance_entry(
                restaurant_id=self.rest_a.id,
                user_id=self.owner_a.id,
                entry_type='expense',
                amount=Decimal('-50.00'),
                note='Invalid negative expense'
            )

    def test_manual_finance_entry_invalid_type_rejected(self):
        """Rejects unsupported finance types."""
        with pytest.raises(ValueError, match="Invalid transaction type"):
            create_manual_finance_entry(
                restaurant_id=self.rest_a.id,
                user_id=self.owner_a.id,
                entry_type='dividend',
                amount=Decimal('100.00')
            )

    def test_manual_finance_entry_update_service(self):
        """Allows updating manual finance entries and logs the previous state in AuditLog."""
        entry = create_manual_finance_entry(
            restaurant_id=self.rest_a.id,
            user_id=self.owner_a.id,
            entry_type='expense',
            amount=Decimal('500.00'),
            note='Initial gas cylinder'
        )

        updated = update_manual_finance_entry(
            entry_id=entry.id,
            restaurant_id=self.rest_a.id,
            user_id=self.manager_a.id,
            entry_type='expense',
            amount=Decimal('550.00'),
            note='Updated gas cylinder refill price'
        )

        assert updated.amount == Decimal('550.00')
        assert updated.note == 'Updated gas cylinder refill price'

        audit = AuditLog.query.filter_by(
            restaurant_id=self.rest_a.id,
            action='FINANCE_ENTRY_UPDATED',
            record_id=entry.id
        ).first()
        assert audit is not None
        assert audit.details['old']['amount'] == '500.00'
        assert audit.details['new']['amount'] == '550.00'

    def test_manual_finance_entry_delete_service(self):
        """Allows deleting manual finance entries and writes details to AuditLog."""
        entry = create_manual_finance_entry(
            restaurant_id=self.rest_a.id,
            user_id=self.owner_a.id,
            entry_type='expense',
            amount=Decimal('300.00'),
            note='Cleaning detergent'
        )
        entry_id = entry.id

        delete_manual_finance_entry(entry_id, self.rest_a.id, self.owner_a.id)

        assert db.session.get(FinanceEntry, entry_id) is None
        audit = AuditLog.query.filter_by(
            restaurant_id=self.rest_a.id,
            action='FINANCE_ENTRY_DELETED',
            record_id=entry_id
        ).first()
        assert audit is not None
        assert audit.details['amount'] == '300.00'

    # ==========================================================================
    # 2. READ-ONLY INVARIANT FOR AUTOMATED POS SALES ENTRIES
    # ==========================================================================

    def test_automated_pos_sales_entry_read_only_protection(self):
        """
        Critical Invariant:
        Entries created automatically from paid orders (order_id is not None)
        are strictly READ-ONLY and CANNOT be edited or deleted.
        """
        # Create and pay a POS order
        order = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_kacchi.id, 'quantity': 2, 'note': ''}]
        )
        # Pay the order
        pay_res = record_order_payment(
            order_id=order.id,
            restaurant_id=self.rest_a.id,
            received_by_id=self.cashier_a.id,
            method='cash',
            amount=order.total,
            cash_received=order.total
        )
        assert pay_res['is_fully_paid'] is True

        # Find the automated sale FinanceEntry
        auto_entry = FinanceEntry.query.filter_by(
            restaurant_id=self.rest_a.id,
            order_id=order.id
        ).first()
        assert auto_entry is not None
        assert auto_entry.type == 'sale'
        assert auto_entry.order_id == order.id

        # Attempt to update via service must raise PermissionError
        with pytest.raises(PermissionError, match="read-only"):
            update_manual_finance_entry(
                entry_id=auto_entry.id,
                restaurant_id=self.rest_a.id,
                user_id=self.owner_a.id,
                entry_type='sale',
                amount=Decimal('100.00')
            )

        # Attempt to delete via service must raise PermissionError
        with pytest.raises(PermissionError, match="cannot be deleted"):
            delete_manual_finance_entry(
                entry_id=auto_entry.id,
                restaurant_id=self.rest_a.id,
                user_id=self.owner_a.id
            )

    def test_web_routes_block_edit_and_delete_on_pos_entries(self):
        """Web routes redirect with error message when attempting to alter an automated POS entry."""
        # Create and pay POS order
        order = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_borhani.id, 'quantity': 1, 'note': ''}]
        )
        record_order_payment(
            order_id=order.id,
            restaurant_id=self.rest_a.id,
            received_by_id=self.cashier_a.id,
            method='cash',
            amount=order.total,
            cash_received=order.total
        )

        auto_entry = FinanceEntry.query.filter_by(order_id=order.id).first()

        # Login as owner
        self.login_user(self.owner_a)

        # Try GET edit page
        res = self.client.get(f'/admin/finance/{auto_entry.id}/edit', follow_redirects=True)
        assert res.status_code == 200
        assert b"read-only and cannot be modified" in res.data

        # Try POST edit
        res_post = self.client.post(f'/admin/finance/{auto_entry.id}/edit', data={
            'type': 'sale',
            'amount': '999.00',
            'entry_date': '2026-11-11',
            'note': 'Hacked price'
        }, follow_redirects=True)
        assert b"read-only and cannot be modified" in res_post.data

        # Try POST delete
        res_del = self.client.post(f'/admin/finance/{auto_entry.id}/delete', follow_redirects=True)
        assert b"read-only and cannot be deleted" in res_del.data

        # Verify entry remains unchanged in DB
        db.session.refresh(auto_entry)
        assert auto_entry.amount == order.total

    # ==========================================================================
    # 3. CASHBOOK LISTING, DATE FILTERS & TOTALS
    # ==========================================================================

    def test_cashbook_listing_filters_and_totals(self):
        """Cashbook list returns paginated entries and filters by type and date range."""
        now = datetime.now(timezone.utc)
        today = now.date()
        yesterday = today - timedelta(days=1)

        # Add today entries
        e_sale = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('1000.00'), 'Catering sale', today)
        e_pur = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'purchase', Decimal('300.00'), 'Meat purchase', today)
        e_exp = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'expense', Decimal('100.00'), 'Electricity bill', today)

        # Add yesterday entry
        e_old = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'purchase', Decimal('400.00'), 'Old purchase', yesterday)

        # Get cashbook without filter
        cb_all = get_finance_cashbook(self.rest_a.id)
        assert cb_all['pagination'].total == 4
        assert cb_all['daily_totals']['sales'] == Decimal('1000.00')
        assert cb_all['daily_totals']['purchases'] == Decimal('300.00')
        assert cb_all['daily_totals']['expenses'] == Decimal('100.00')
        assert cb_all['daily_totals']['net'] == Decimal('600.00')

        # Filter by type = 'purchase'
        cb_pur = get_finance_cashbook(self.rest_a.id, entry_type='purchase')
        assert cb_pur['pagination'].total == 2
        for item in cb_pur['entries']:
            assert item.type == 'purchase'

        # Filter by date range (only today)
        cb_today = get_finance_cashbook(self.rest_a.id, start_date=today, end_date=today)
        assert cb_today['pagination'].total == 3

    # ==========================================================================
    # 4. DASHBOARD RECONCILIATION & DAY-OVER-DAY COMPARISON
    # ==========================================================================

    def test_dashboard_reconciliation_exactness(self):
        """
        The dashboard totals must match the orders and finance entries exactly.
        Verifies:
          - Total Sales == Sum of FinanceEntry(type='sale')
          - Paid total == Sum of Order.total for paid orders
          - Unpaid total == Sum of Order.total for open orders
          - Net profit == Total Sales - (Purchases + Expenses)
        """
        today = datetime.now(timezone.utc).date()

        # 1. Place Order 1: 2x Kacchi (450 * 2 = 900) + 5% VAT (45) = 945.00 -> Paid
        order_paid = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_kacchi.id, 'quantity': 2, 'note': ''}]
        )
        record_order_payment(
            order_id=order_paid.id,
            restaurant_id=self.rest_a.id,
            received_by_id=self.cashier_a.id,
            method='bkash',
            amount=order_paid.total,
            reference='TRX9988'
        )

        # 2. Place Order 2: 1x Borhani (80) + 5% VAT (4) = 84.00 -> Unpaid/Open
        order_unpaid = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_borhani.id, 'quantity': 1, 'note': ''}]
        )

        # 3. Add manual finance entries
        manual_pur = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'purchase', Decimal('200.00'), 'Vegetables', today)
        manual_exp = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'expense', Decimal('50.00'), 'Delivery fuel', today)
        manual_sale = create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('500.00'), 'Private event advance', today)

        # Fetch dashboard metrics
        metrics = get_dashboard_metrics(self.rest_a.id, user_role='owner')
        kpis = metrics['kpi_cards']

        # Expected totals:
        # Sales: order_paid.total (945.00) + manual_sale (500.00) = 1445.00
        expected_sales = order_paid.total + Decimal('500.00')
        assert kpis['sales']['value'] == expected_sales

        # Paid orders total: exactly order_paid.total (945.00)
        assert kpis['paid']['value'] == order_paid.total
        assert kpis['paid']['count'] == 1

        # Unpaid orders total: exactly order_unpaid.total (84.00)
        assert kpis['unpaid']['value'] == order_unpaid.total
        assert kpis['unpaid']['count'] == 1

        # Purchases: 200.00
        assert kpis['expenses']['value'] == Decimal('50.00')
        assert kpis['purchases']['value'] == Decimal('200.00')

        # Net balance: 1445.00 - (200.00 + 50.00) = 1195.00
        expected_net = expected_sales - (Decimal('200.00') + Decimal('50.00'))
        assert kpis['net']['value'] == expected_net

    def test_dashboard_day_over_day_comparison(self):
        """Verifies day-over-day delta comparisons against yesterday's metrics."""
        now = datetime.now(timezone.utc)
        today = now.date()
        yesterday = today - timedelta(days=1)

        # Yesterday sales: ৳1000
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('1000.00'), 'Yesterday Sale', yesterday)
        # Today sales: ৳1500 (+৳500 / +50%)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('1500.00'), 'Today Sale', today)

        metrics = get_dashboard_metrics(self.rest_a.id, user_role='owner')
        sales_card = metrics['kpi_cards']['sales']

        assert sales_card['value'] == Decimal('1500.00')
        assert sales_card['yesterday_value'] == Decimal('1000.00')
        assert sales_card['diff'] == Decimal('500.00')
        assert sales_card['pct'] == 50.0
        assert sales_card['direction'] == 'up'

    # ==========================================================================
    # 5. TOP 5 SELLING DISHES RANKING
    # ==========================================================================

    def test_top_selling_dishes_aggregation(self):
        """Verifies top 5 selling dishes are sorted by quantity sold with revenue snapshots."""
        # Order 1: 5x Kacchi, 2x Borhani
        order1 = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[
                {'dish_id': self.dish_kacchi.id, 'quantity': 5, 'note': ''},
                {'dish_id': self.dish_borhani.id, 'quantity': 2, 'note': ''}
            ]
        )
        # Order 2: 3x Borhani, 1x Kabab
        order2 = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[
                {'dish_id': self.dish_borhani.id, 'quantity': 3, 'note': ''},
                {'dish_id': self.dish_kabab.id, 'quantity': 1, 'note': ''}
            ]
        )

        metrics = get_dashboard_metrics(self.rest_a.id, user_role='owner')
        top_dishes = metrics['top_dishes']

        # Total sold:
        # Kacchi: 5 portions (revenue: 5 * 450 = 2250.00)
        # Borhani: 5 portions (revenue: 5 * 80 = 400.00)
        # Kabab: 1 portion (revenue: 1 * 70 = 70.00)
        assert len(top_dishes) == 3
        dish_names = [d['name'] for d in top_dishes]
        assert "Mutton Kacchi Basmati" in dish_names
        assert "Borhani 250ml" in dish_names
        assert "Jali Kabab" in dish_names

        # Find Kacchi item in top dishes
        kacchi_stat = next(d for d in top_dishes if d['name'] == "Mutton Kacchi Basmati")
        assert kacchi_stat['quantity'] == 5
        assert kacchi_stat['revenue'] == Decimal('2250.00')

    # ==========================================================================
    # 6. ROLE-BASED DASHBOARD PERSPECTIVES
    # ==========================================================================

    def test_owner_and_manager_dashboard_web_views(self):
        """
        Owner sees complete financial cards (Net Balance, Expenses, Purchases, Total Sales).
        Manager sees operational view without owner-only financial totals.
        """
        # 1. Login as Owner
        self.login_user(self.owner_a)
        res_owner = self.client.get('/admin/')
        assert res_owner.status_code == 200
        assert b"Executive Analytics &amp; Finance" in res_owner.data
        assert b"Net Balance Today" in res_owner.data
        assert b"Operating Expenses" in res_owner.data
        assert b"Kitchen Purchases" in res_owner.data

        # 2. Login as Manager
        self.login_user(self.manager_a)
        res_manager = self.client.get('/admin/')
        assert res_manager.status_code == 200
        assert b"Operations &amp; Floor Dashboard" in res_manager.data
        assert b"Manager Operational Perspective" in res_manager.data
        assert b"Orders Placed Today" in res_manager.data
        assert b"Table Occupancy" in res_manager.data
        # Sensitive bottom-line financial cards are hidden from Manager
        assert b"Net Balance Today" not in res_manager.data
        assert b"Operating Expenses" not in res_manager.data
        assert b"Kitchen Purchases" not in res_manager.data

    def test_cashier_and_kitchen_forbidden_from_admin_and_finance(self):
        """Cashier role cannot access /admin/ or /admin/finance."""
        self.login_user(self.cashier_a)

        res_dash = self.client.get('/admin/')
        assert res_dash.status_code == 403

        res_fin = self.client.get('/admin/finance')
        assert res_fin.status_code == 403

    # ==========================================================================
    # 7. MULTI-TENANT ISOLATION
    # ==========================================================================

    def test_multi_tenant_data_isolation(self):
        """Tenant B cannot see, edit, or delete Tenant A's finance entries."""
        entry_a = create_manual_finance_entry(
            restaurant_id=self.rest_a.id,
            user_id=self.owner_a.id,
            entry_type='expense',
            amount=Decimal('800.00'),
            note='Secret Restaurant A expense'
        )

        # Login as Owner B (Restaurant B)
        self.login_user(self.owner_b)

        # Cashbook listing for Tenant B must be empty
        res_list = self.client.get('/admin/finance')
        assert res_list.status_code == 200
        assert b"Secret Restaurant A expense" not in res_list.data

        # Tenant B attempting to access or edit Tenant A's entry gets 404
        res_edit = self.client.get(f'/admin/finance/{entry_a.id}/edit')
        assert res_edit.status_code == 404

        res_post_edit = self.client.post(f'/admin/finance/{entry_a.id}/edit', data={
            'type': 'expense',
            'amount': '1.00',
            'entry_date': '2026-11-11'
        })
        assert res_post_edit.status_code == 404

        res_del = self.client.post(f'/admin/finance/{entry_a.id}/delete')
        assert res_del.status_code == 404

        # Entry A remains unchanged
        db.session.refresh(entry_a)
        assert entry_a.amount == Decimal('800.00')
