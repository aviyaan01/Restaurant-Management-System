import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import io
import csv
import unittest
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal

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
from app.services.billing_service import record_order_payment
from app.services.order_service import create_pos_order
from app.services.finance_service import create_manual_finance_entry
from app.services.audit_service import get_audit_logs, export_audit_logs_csv
from app.services.export_service import export_finance_csv, export_orders_csv

class TestConfig:
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'hardening-test-secret-key-step-12'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class TestStep12SecurityHardening(unittest.TestCase):
    """
    Test suite for Step 12: Audit Log, Security Hardening, and Multi-Tenant Isolation.
    """

    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant A (Primary Tenant)
        self.rest_a = Restaurant(
            name="Sultan's Dine Dhanmondi",
            phone="01711111111",
            address="Dhanmondi, Dhaka",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        # Seed Restaurant B (Adversary / Independent Tenant)
        self.rest_b = Restaurant(
            name="Kacchi Bhai Banani",
            phone="01722222222",
            address="Banani, Dhaka",
            bin="987654321-0202",
            vat_rate=Decimal("10.00"),
            price_mode="inclusive"
        )
        db.session.add_all([self.rest_a, self.rest_b])
        db.session.commit()

        # Seed Users for Restaurant A
        self.owner_a = User(
            restaurant_id=self.rest_a.id,
            name="SD Owner",
            email="owner@sultans.com",
            phone="01710000001",
            role="owner",
            is_active=True
        )
        self.owner_a.set_password("OwnerSecurePass123!")

        self.manager_a = User(
            restaurant_id=self.rest_a.id,
            name="SD Manager",
            email="manager@sultans.com",
            phone="01710000002",
            role="manager",
            is_active=True
        )
        self.manager_a.set_password("ManagerSecurePass123!")

        self.cashier_a = User(
            restaurant_id=self.rest_a.id,
            name="SD Cashier",
            email="cashier@sultans.com",
            phone="01710000003",
            role="cashier",
            is_active=True
        )
        self.cashier_a.set_password("CashierSecurePass123!")

        self.kitchen_a = User(
            restaurant_id=self.rest_a.id,
            name="SD Chef",
            email="chef@sultans.com",
            phone="01710000004",
            role="kitchen",
            is_active=True
        )
        self.kitchen_a.set_password("ChefSecurePass123!")

        # Seed Users for Restaurant B
        self.owner_b = User(
            restaurant_id=self.rest_b.id,
            name="KB Owner",
            email="owner@kacchibhai.com",
            phone="01720000001",
            role="owner",
            is_active=True
        )
        self.owner_b.set_password("OwnerBSecurePass123!")

        self.cashier_b = User(
            restaurant_id=self.rest_b.id,
            name="KB Cashier",
            email="cashier@kacchibhai.com",
            phone="01720000002",
            role="cashier",
            is_active=True
        )
        self.cashier_b.set_password("CashierBSecurePass123!")

        db.session.add_all([
            self.owner_a, self.manager_a, self.cashier_a, self.kitchen_a,
            self.owner_b, self.cashier_b
        ])
        db.session.commit()

        # Seed Menu & Table for Restaurant A
        self.cat_a = Category(restaurant_id=self.rest_a.id, name="Biryani", sort_order=1)
        db.session.add(self.cat_a)
        db.session.commit()

        self.dish_a = Dish(
            restaurant_id=self.rest_a.id,
            category_id=self.cat_a.id,
            name="Kacchi Platter",
            price=Decimal("500.00"),
            veg_type="non-veg",
            is_available=True
        )
        self.space_a = Space(restaurant_id=self.rest_a.id, name="Ground Floor")
        db.session.add_all([self.dish_a, self.space_a])
        db.session.commit()

        self.table_a = Table(restaurant_id=self.rest_a.id, space_id=self.space_a.id, name="T-01", capacity=4)
        db.session.add(self.table_a)
        db.session.commit()

        # Seed Menu & Table for Restaurant B
        self.cat_b = Category(restaurant_id=self.rest_b.id, name="Beverage", sort_order=1)
        db.session.add(self.cat_b)
        db.session.commit()

        self.dish_b = Dish(
            restaurant_id=self.rest_b.id,
            category_id=self.cat_b.id,
            name="Borhani",
            price=Decimal("90.00"),
            veg_type="veg",
            is_available=True
        )
        self.space_b = Space(restaurant_id=self.rest_b.id, name="Rooftop")
        db.session.add_all([self.dish_b, self.space_b])
        db.session.commit()

        self.table_b = Table(restaurant_id=self.rest_b.id, space_id=self.space_b.id, name="KB-01", capacity=2)
        db.session.add(self.table_b)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_user(self, user, password=None):
        """Helper to cleanly log in a user after ending existing session."""
        self.client.get('/auth/logout')
        pwd = password
        if pwd is None:
            if user.id == self.owner_a.id: pwd = "OwnerSecurePass123!"
            elif user.id == self.manager_a.id: pwd = "ManagerSecurePass123!"
            elif user.id == self.cashier_a.id: pwd = "CashierSecurePass123!"
            elif user.id == self.kitchen_a.id: pwd = "ChefSecurePass123!"
            elif user.id == self.owner_b.id: pwd = "OwnerBSecurePass123!"
            elif user.id == self.cashier_b.id: pwd = "CashierBSecurePass123!"

        return self.client.post('/auth/login', data={
            'identifier': user.email,
            'password': pwd
        }, follow_redirects=True)

    # ==========================================================================
    # 1. AUTHENTICATION, RATE LIMITING & LOCKOUT (5 ATTEMPTS)
    # ==========================================================================

    def test_account_lockout_after_five_failed_logins(self):
        """5 consecutive failed logins trigger a 15-minute lockout."""
        target_user = self.cashier_a

        # 4 consecutive bad attempts
        for attempt in range(1, 5):
            res = self.client.post('/auth/login', data={
                'identifier': target_user.email,
                'password': 'WrongPassword123'
            }, follow_redirects=True)
            assert res.status_code == 200
            db.session.refresh(target_user)
            assert target_user.failed_login_count == attempt
            assert target_user.locked_until is None

        # 5th bad attempt -> Lockout triggers!
        res_5th = self.client.post('/auth/login', data={
            'identifier': target_user.email,
            'password': 'WrongPassword123'
        }, follow_redirects=True)
        assert res_5th.status_code == 200
        assert b"temporarily locked for 15 minutes" in res_5th.data

        db.session.refresh(target_user)
        assert target_user.failed_login_count == 5
        assert target_user.locked_until is not None

        # Verify ACCOUNT_LOCKED was written to AuditLog
        lock_audit = AuditLog.query.filter_by(
            restaurant_id=self.rest_a.id,
            action='ACCOUNT_LOCKED',
            record_id=target_user.id
        ).first()
        assert lock_audit is not None
        assert lock_audit.details['failed_attempts'] == 5

        # 6th attempt with CORRECT password is still locked out!
        res_locked = self.client.post('/auth/login', data={
            'identifier': target_user.email,
            'password': 'CashierSecurePass123!'
        }, follow_redirects=True)
        assert res_locked.status_code == 200
        assert b"Account temporarily locked" in res_locked.data

    # ==========================================================================
    # 2. ROLE BOUNDARIES & DECORATOR ENFORCEMENT
    # ==========================================================================

    def test_role_boundary_enforcement(self):
        """Validates that routes block unauthorized roles with HTTP 403 Forbidden."""
        # Cashier: cannot view Admin Dashboard, Staff, Settings, or Audit
        self.login_user(self.cashier_a)
        assert self.client.get('/admin/').status_code == 403
        assert self.client.get('/admin/staff').status_code == 403
        assert self.client.get('/admin/settings').status_code == 403
        assert self.client.get('/admin/audit').status_code == 403
        assert self.client.get('/admin/finance').status_code == 403

        # Kitchen Chef: cannot view POS terminal, Orders list, or Admin
        self.login_user(self.kitchen_a)
        assert self.client.get('/pos/').status_code == 403
        assert self.client.get('/pos/orders').status_code == 403
        assert self.client.get('/admin/').status_code == 403

        # Manager: can view Dashboard, Finance, and Audit, but blocked from Staff, Settings, and Audit CSV export
        self.login_user(self.manager_a)
        assert self.client.get('/admin/').status_code == 200
        assert self.client.get('/admin/finance').status_code == 200
        assert self.client.get('/admin/audit').status_code == 200
        assert self.client.get('/admin/staff').status_code == 403
        assert self.client.get('/admin/settings').status_code == 403
        assert self.client.get('/admin/audit/export.csv').status_code == 403

        # Unauthenticated request redirects to /auth/login
        self.client.get('/auth/logout')
        res_unauth = self.client.get('/admin/', follow_redirects=False)
        assert res_unauth.status_code == 302
        assert '/auth/login' in res_unauth.headers['Location']

    # ==========================================================================
    # 3. MULTI-TENANT DATA ISOLATION (URL & ID GUESSING ACROSS RESTAURANTS)
    # ==========================================================================

    def test_cross_tenant_url_and_id_guessing_blocked(self):
        """
        Adversary Test:
        User from Restaurant B guesses IDs belonging to Restaurant A across all modules.
        Every query must return 404 Not Found without leaking existence or data.
        """
        # Create Order in Restaurant A
        order_a = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish_a.id, 'quantity': 2, 'note': ''}],
            table_id=self.table_a.id
        )
        record_order_payment(
            order_id=order_a.id,
            restaurant_id=self.rest_a.id,
            received_by_id=self.cashier_a.id,
            method='cash',
            amount=order_a.total,
            cash_received=order_a.total
        )
        finance_a = FinanceEntry.query.filter_by(order_id=order_a.id).first()

        # Login as Cashier B (Restaurant B)
        self.login_user(self.cashier_b)

        # 1. Try viewing Order A
        assert self.client.get(f'/pos/orders/{order_a.id}').status_code == 404
        # 2. Try paying Order A
        assert self.client.get(f'/pos/orders/{order_a.id}/pay').status_code == 404
        assert self.client.post(f'/pos/orders/{order_a.id}/pay', data={'method': 'cash', 'amount': '10.00'}).status_code == 404
        # 3. Try receipt of Order A
        assert self.client.get(f'/pos/orders/{order_a.id}/receipt').status_code == 404
        # 4. Try KOT slip of Order A
        assert self.client.get(f'/pos/orders/{order_a.id}/kot').status_code == 404
        # 5. Try appending items to Order A
        assert self.client.get(f'/pos/orders/{order_a.id}/append').status_code == 404

        # Login as Owner B (Restaurant B)
        self.login_user(self.owner_b)

        # 6. Try cancelling Order A
        assert self.client.post(f'/pos/orders/{order_a.id}/cancel', data={'reason': 'Cross-tenant cancel'}).status_code == 404
        # 7. Try editing Dish A
        assert self.client.get(f'/admin/dishes/{self.dish_a.id}/edit').status_code == 404
        assert self.client.post(f'/admin/dishes/{self.dish_a.id}/delete').status_code == 404
        assert self.client.post(f'/admin/dishes/{self.dish_a.id}/toggle-available').status_code == 404
        # 8. Try editing Table A
        assert self.client.get(f'/admin/tables/{self.table_a.id}/edit').status_code == 404
        assert self.client.post(f'/admin/tables/{self.table_a.id}/delete').status_code == 404
        assert self.client.post(f'/admin/tables/{self.table_a.id}/toggle-status').status_code == 404
        # 9. Try editing Space A
        assert self.client.get(f'/admin/spaces/{self.space_a.id}/edit').status_code == 404
        assert self.client.post(f'/admin/spaces/{self.space_a.id}/delete').status_code == 404
        # 10. Try editing Staff A
        assert self.client.get(f'/admin/staff/{self.cashier_a.id}/edit').status_code == 404
        assert self.client.post(f'/admin/staff/{self.cashier_a.id}/toggle-status').status_code == 404
        # 11. Try editing Finance Entry A
        assert self.client.get(f'/admin/finance/{finance_a.id}/edit').status_code == 404
        assert self.client.post(f'/admin/finance/{finance_a.id}/delete').status_code == 404

        # 12. Audit log data isolation: Owner B views /admin/audit
        res_audit = self.client.get('/admin/audit')
        assert res_audit.status_code == 200
        assert b"Sultan's Dine" not in res_audit.data
        assert b"Kacchi Platter" not in res_audit.data

    # ==========================================================================
    # 4. AUDIT LOG FILTERING & IMMUTABILITY
    # ==========================================================================

    def test_audit_log_filters_and_immutability(self):
        """Verifies filtering by action, user, record_type, and date range; records cannot be mutated."""
        today = date.today()

        # Generate audit events
        self.login_user(self.owner_a)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'expense', Decimal('250.00'), 'Test Expense', today)

        # 1. Filter by action
        res_action = self.client.get('/admin/audit?action=FINANCE_ENTRY_CREATED')
        assert res_action.status_code == 200
        assert b"FINANCE_ENTRY_CREATED" in res_action.data

        # 2. Filter by record_type
        res_type = self.client.get('/admin/audit?record_type=FinanceEntry')
        assert res_type.status_code == 200
        assert b"FinanceEntry" in res_type.data

        # 3. Filter by user
        res_user = self.client.get(f'/admin/audit?user_id={self.owner_a.id}')
        assert res_user.status_code == 200
        assert b"SD Owner" in res_user.data

        # 4. Filter by date
        res_date = self.client.get(f'/admin/audit?start_date={today}&end_date={today}')
        assert res_date.status_code == 200

        # 5. Immutability guarantee: Assert no mutation routes exist for audit logs
        # Attempting POST, PUT, DELETE on /admin/audit yields 405 Method Not Allowed
        assert self.client.post('/admin/audit').status_code == 405
        assert self.client.delete('/admin/audit').status_code == 405
        assert self.client.post('/admin/audit/1/delete').status_code == 404
        assert self.client.post('/admin/audit/1/edit').status_code == 404

    # ==========================================================================
    # 5. CSV EXPORTS & EXACT TOTAL RECONCILIATION
    # ==========================================================================

    def test_finance_csv_export_totals_reconciliation(self):
        """Exported CSV totals must match on-screen finance cashbook totals exactly."""
        today = date.today()

        # Seed manual entries: 2 sales (1000 + 500 = 1500), 1 purchase (400), 1 expense (150)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('1000.00'), 'Sale 1', today)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'sale', Decimal('500.00'), 'Sale 2', today)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'purchase', Decimal('400.00'), 'Purchase 1', today)
        create_manual_finance_entry(self.rest_a.id, self.owner_a.id, 'expense', Decimal('150.00'), 'Expense 1', today)

        expected_sales = Decimal('1500.00')
        expected_purchases = Decimal('400.00')
        expected_expenses = Decimal('150.00')
        expected_net = expected_sales - (expected_purchases + expected_expenses)  # 950.00

        self.login_user(self.owner_a)
        res = self.client.get('/admin/finance/export.csv')
        assert res.status_code == 200
        assert res.mimetype == 'text/csv'
        assert 'attachment' in res.headers['Content-Disposition']

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))

        # Find summary rows
        summary_dict = {}
        for row in reader:
            if len(row) >= 5 and (row[0].startswith("Total") or row[0].startswith("Net")):
                summary_dict[row[0]] = Decimal(row[4])

        assert summary_dict['Total Sales (BDT)'] == expected_sales
        assert summary_dict['Total Purchases (BDT)'] == expected_purchases
        assert summary_dict['Total Expenses (BDT)'] == expected_expenses
        assert summary_dict['Net Balance (BDT)'] == expected_net

    def test_orders_csv_export_totals_reconciliation(self):
        """Exported Orders CSV totals must equal the sum of order totals on screen."""
        # Create 2 orders in Restaurant A
        order1 = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_a.id, 'quantity': 1, 'note': ''}]  # 500 + 5% = 525.00
        )
        order2 = create_pos_order(
            restaurant_id=self.rest_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_a.id, 'quantity': 3, 'note': ''}]  # 1500 + 5% = 1575.00
        )

        expected_total = order1.total + order2.total
        expected_subtotal = order1.subtotal + order2.subtotal
        expected_vat = order1.vat_amount + order2.vat_amount

        self.login_user(self.owner_a)
        res = self.client.get('/admin/orders/export.csv')
        assert res.status_code == 200
        assert res.mimetype == 'text/csv'

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))

        # Find TOTAL row
        total_row = next(r for r in reader if len(r) > 0 and r[0] == 'TOTAL')
        # Row format: ["TOTAL", "", "", "", "", "2 orders", subtotal, discount, cover, vat, total, ""]
        assert Decimal(total_row[6]) == expected_subtotal
        assert Decimal(total_row[9]) == expected_vat
        assert Decimal(total_row[10]) == expected_total

    def test_audit_logs_csv_export(self):
        """Owner can export audit logs to CSV; includes headers, staff, action, and JSON payload."""
        self.login_user(self.owner_a)
        res = self.client.get('/admin/audit/export.csv')
        assert res.status_code == 200
        assert res.mimetype == 'text/csv'

        csv_text = res.data.decode('utf-8')
        reader = list(csv.reader(io.StringIO(csv_text)))
        header = reader[0]

        assert "Log ID" in header
        assert "Timestamp (UTC)" in header
        assert "Staff Name" in header
        assert "Action" in header
        assert "Details JSON" in header

    # ==========================================================================
    # 6. SECURITY HEADERS
    # ==========================================================================

    def test_security_headers_present_on_all_responses(self):
        """Verifies standard defense-in-depth HTTP security headers on responses."""
        res = self.client.get('/')
        assert res.status_code == 200
        assert res.headers.get('X-Content-Type-Options') == 'nosniff'
        assert res.headers.get('X-Frame-Options') == 'SAMEORIGIN'
        assert res.headers.get('X-XSS-Protection') == '1; mode=block'
        assert res.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
        # In non-debug mode (DEBUG=False in TestConfig), HSTS is set
        assert 'Strict-Transport-Security' in res.headers
