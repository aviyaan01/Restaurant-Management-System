import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import unittest
from datetime import timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.services.order_service import create_pos_order
from app.services.billing_service import record_order_payment

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-10'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step10PrintingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant A (5% exclusive VAT)
        self.restaurant_a = Restaurant(
            name="Kacchi Bhai",
            phone="01711223344",
            address="Road 11, Banani, Dhaka-1213",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive",
            receipt_footer="ধন্যবাদ, আবার আসবেন!\nThank you for dining with us."
        )

        # Seed Restaurant B (Multi-tenancy isolation)
        self.restaurant_b = Restaurant(
            name="Sultan's Dine",
            phone="01799887766",
            address="Dhanmondi, Dhaka",
            bin="987654321-0202",
            vat_rate=Decimal("10.00"),
            price_mode="inclusive",
            receipt_footer="Visit again soon!"
        )
        db.session.add_all([self.restaurant_a, self.restaurant_b])
        db.session.commit()

        # Seed Users for Restaurant A: Owner, Manager, Cashier, Kitchen
        self.owner_a = User(
            restaurant_id=self.restaurant_a.id,
            name="KB Owner",
            email="owner@kacchi.com",
            phone="01711111101",
            role="owner",
            is_active=True
        )
        self.owner_a.set_password("ownerPass123")

        self.manager_a = User(
            restaurant_id=self.restaurant_a.id,
            name="KB Manager",
            email="manager@kacchi.com",
            phone="01711111102",
            role="manager",
            is_active=True
        )
        self.manager_a.set_password("managerPass123")

        self.cashier_a = User(
            restaurant_id=self.restaurant_a.id,
            name="KB Cashier",
            email="cashier@kacchi.com",
            phone="01711111103",
            role="cashier",
            is_active=True
        )
        self.cashier_a.set_password("cashierPass123")

        self.kitchen_a = User(
            restaurant_id=self.restaurant_a.id,
            name="KB Chef",
            email="chef@kacchi.com",
            phone="01711111104",
            role="kitchen",
            is_active=True
        )
        self.kitchen_a.set_password("chefPass123")

        # Seed User for Restaurant B
        self.cashier_b = User(
            restaurant_id=self.restaurant_b.id,
            name="SD Cashier",
            email="cashier@sultans.com",
            phone="01722222201",
            role="cashier",
            is_active=True
        )
        self.cashier_b.set_password("cashierBPass123")

        db.session.add_all([self.owner_a, self.manager_a, self.cashier_a, self.kitchen_a, self.cashier_b])
        db.session.commit()

        # Seed Dining Table for Restaurant A
        self.space_a = Space(restaurant_id=self.restaurant_a.id, name="Main Dining")
        db.session.add(self.space_a)
        db.session.flush()

        self.table_a = Table(
            restaurant_id=self.restaurant_a.id,
            space_id=self.space_a.id,
            name="T-07",
            capacity=4,
            cover_charge=Decimal("25.00"),
            status="open"
        )
        db.session.add(self.table_a)

        # Seed Dishes for Restaurant A
        self.cat_a = Category(restaurant_id=self.restaurant_a.id, name="Biryani")
        db.session.add(self.cat_a)
        db.session.flush()

        self.dish_a1 = Dish(
            restaurant_id=self.restaurant_a.id,
            category_id=self.cat_a.id,
            name="Basmati Mutton Kacchi",
            price=Decimal("480.00"),
            discount=Decimal("30.00"),  # effective unit price = 450.00
            is_available=True
        )
        self.dish_a2 = Dish(
            restaurant_id=self.restaurant_a.id,
            category_id=self.cat_a.id,
            name="Special Borhani",
            price=Decimal("80.00"),
            discount=Decimal("0.00"),
            is_available=True
        )
        db.session.add_all([self.dish_a1, self.dish_a2])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_as(self, email, password):
        self.client.get('/auth/logout')
        return self.client.post('/auth/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # ==========================================================================
    # 1. CUSTOMER RECEIPT TESTING
    # ==========================================================================

    def test_customer_receipt_content_and_rbac(self):
        """
        Customer Receipt Verification:
          - Accessible by Cashier, Manager, Owner.
          - Inaccessible by Kitchen staff (403 Forbidden).
          - Unauthenticated redirected to login.
          - Displays restaurant name, address, phone, BIN, order #, table, date/time, cashier.
          - Displays line items (quantity, snapshot name, unit price, total).
          - Displays subtotal, discount, cover charge, VAT, total.
          - Displays payment method breakdown, cash tendered, change due.
          - Displays Bengali receipt footer.
        """
        # Create and pay a Dine-In Order
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.cashier_a.id,
            order_type='dine_in',
            items_data=[
                {'dish_id': self.dish_a1.id, 'quantity': 2, 'note': 'Extra aloo'},
                {'dish_id': self.dish_a2.id, 'quantity': 1}
            ],
            table_id=self.table_a.id
        )

        # Record payment via Cash (paying ৳1100 for ৳1055.25 bill)
        record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant_a.id,
            received_by_id=self.cashier_a.id,
            method='cash',
            amount=order.total,
            cash_received=Decimal('1100.00')
        )

        # 1. Cashier views receipt
        self.login_as(self.cashier_a.email, "cashierPass123")
        res = self.client.get(f'/pos/orders/{order.id}/receipt')
        assert res.status_code == 200

        # Check Branding & Tax
        assert b"Kacchi Bhai" in res.data
        assert b"Road 11, Banani" in res.data
        assert b"01711223344" in res.data
        assert b"123456789-0101" in res.data
        assert b"SALES RECEIPT" in res.data or b"MUSAK-6.3" in res.data

        # Check Order Metadata
        assert f"#{order.order_no}".encode() in res.data
        assert b"T-07" in res.data
        assert b"KB Cashier" in res.data

        # Check Item Snapshots & Notes
        assert b"Basmati Mutton Kacchi" in res.data
        assert b"Special Borhani" in res.data
        assert b"Extra aloo" in res.data

        # Check Financial Breakdown & Totals
        assert b"Subtotal" in res.data
        assert b"VAT" in res.data
        assert b"NET TOTAL" in res.data
        assert f"৳{order.total:.2f}".encode() in res.data

        # Check Payments & Change Due
        assert b"Cash" in res.data
        assert b"Change Returned" in res.data

        # Check Bengali receipt footer
        assert "ধন্যবাদ, আবার আসবেন!".encode('utf-8') in res.data

        # 2. Kitchen staff blocked from customer sales receipt
        self.login_as(self.kitchen_a.email, "chefPass123")
        res_k = self.client.get(f'/pos/orders/{order.id}/receipt')
        assert res_k.status_code == 403

        # 3. Unauthenticated redirected
        self.client.get('/auth/logout')
        res_unauth = self.client.get(f'/pos/orders/{order.id}/receipt')
        assert res_unauth.status_code == 302

    def test_customer_receipt_width_options_and_autoprint(self):
        """
        Receipt supports selectable 80mm and 58mm thermal paper widths
        and autoprint trigger via ?autoprint=1.
        """
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_a2.id, 'quantity': 1}]
        )

        self.login_as(self.cashier_a.email, "cashierPass123")

        # 1. Default 80mm width
        res_80 = self.client.get(f'/pos/orders/{order.id}/receipt?width=80')
        assert res_80.status_code == 200
        assert b"thermal-80" in res_80.data
        assert b"screen-80" in res_80.data

        # 2. Compact 58mm width
        res_58 = self.client.get(f'/pos/orders/{order.id}/receipt?width=58')
        assert res_58.status_code == 200
        assert b"thermal-58" in res_58.data
        assert b"screen-58" in res_58.data

        # 3. Autoprint parameter
        res_auto = self.client.get(f'/pos/orders/{order.id}/receipt?autoprint=1')
        assert res_auto.status_code == 200
        assert b"window.print()" in res_auto.data

    # ==========================================================================
    # 2. KITCHEN ORDER TICKET (KOT) SLIP TESTING
    # ==========================================================================

    def test_kot_slip_content_and_invariants(self):
        """
        KOT Slip Verification:
          - Accessible by Kitchen, Cashier, Manager, Owner.
          - Contains Order #, Table, Server, items, and preparation notes.
          - STRICT INVARIANT: ZERO prices, ZERO subtotal, ZERO VAT, ZERO total BDT!
        """
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.cashier_a.id,
            order_type='dine_in',
            items_data=[
                {'dish_id': self.dish_a1.id, 'quantity': 3, 'note': 'झाल कम / Less spicy'},
                {'dish_id': self.dish_a2.id, 'quantity': 2, 'note': 'Cold'}
            ],
            table_id=self.table_a.id
        )

        # Kitchen chef can access KOT
        self.login_as(self.kitchen_a.email, "chefPass123")
        res = self.client.get(f'/pos/orders/{order.id}/kot')
        assert res.status_code == 200

        # Kitchen Banner & Order Metadata
        assert b"KITCHEN ORDER TICKET" in res.data
        assert f"KOT #{order.order_no}".encode() in res.data
        assert b"TABLE: T-07" in res.data
        assert b"KB Cashier" in res.data

        # Items and Quantities
        assert b"[3]" in res.data
        assert b"Basmati Mutton Kacchi" in res.data
        assert "झाल कम / Less spicy".encode('utf-8') in res.data
        assert b"[2]" in res.data
        assert b"Special Borhani" in res.data
        assert b"Cold" in res.data
        assert b"Total Items:" in res.data
        assert b"2 (5 Portions)" in res.data

        # STRICT INVARIANT: NO PRICES OR AMOUNTS
        assert b"480.00" not in res.data
        assert b"450.00" not in res.data
        assert b"80.00" not in res.data
        assert b"Subtotal" not in res.data
        assert b"VAT" not in res.data
        assert b"Total Payable" not in res.data
        assert b"NET TOTAL" not in res.data
        assert b"Tk" not in res.data

    def test_kot_width_options_and_autoprint(self):
        """KOT supports 80mm and 58mm widths and autoprint script."""
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.cashier_a.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_a2.id, 'quantity': 1}]
        )

        self.login_as(self.kitchen_a.email, "chefPass123")

        # 80mm KOT
        res_80 = self.client.get(f'/pos/orders/{order.id}/kot?width=80')
        assert res_80.status_code == 200
        assert b"kot-80" in res_80.data

        # 58mm KOT
        res_58 = self.client.get(f'/pos/orders/{order.id}/kot?width=58')
        assert res_58.status_code == 200
        assert b"kot-58" in res_58.data

        # Autoprint
        res_auto = self.client.get(f'/pos/orders/{order.id}/kot?autoprint=1')
        assert res_auto.status_code == 200
        assert b"window.print()" in res_auto.data

    # ==========================================================================
    # 3. MULTI-TENANT ISOLATION (NON-NEGOTIABLE RULE 1)
    # ==========================================================================

    def test_printing_multi_tenant_isolation(self):
        """
        User from Restaurant B CANNOT access, view, or print
        Customer Receipt or KOT slip for an order belonging to Restaurant A.
        Must return 404 Not Found.
        """
        order_a = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.cashier_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_a1.id, 'quantity': 1}]
        )

        # Log in as Cashier from Restaurant B
        self.login_as(self.cashier_b.email, "cashierBPass123")

        # Attempt to access Restaurant A's Customer Receipt
        res_receipt = self.client.get(f'/pos/orders/{order_a.id}/receipt')
        assert res_receipt.status_code == 404

        # Attempt to access Restaurant A's KOT
        res_kot = self.client.get(f'/pos/orders/{order_a.id}/kot')
        assert res_kot.status_code == 404
