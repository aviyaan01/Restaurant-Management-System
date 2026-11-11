import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
from app.models.audit import AuditLog
from app.services.order_service import (
    calculate_order_financials,
    create_pos_order,
    append_items_to_pos_order,
    cancel_pos_order
)

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-7'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step7POSTerminalTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant (5% exclusive VAT)
        self.restaurant = Restaurant(
            name="Kacchi Bhai",
            phone="01711111111",
            address="Banani, Dhaka",
            bin="123456789-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        db.session.add(self.restaurant)
        db.session.commit()

        # Seed Users: Owner, Manager, Cashier, Kitchen
        self.owner = User(
            restaurant_id=self.restaurant.id,
            name="KB Owner",
            email="owner@kacchi.com",
            phone="01711111101",
            role="owner",
            is_active=True
        )
        self.owner.set_password("ownerPass123")

        self.manager = User(
            restaurant_id=self.restaurant.id,
            name="KB Manager",
            email="manager@kacchi.com",
            phone="01711111102",
            role="manager",
            is_active=True
        )
        self.manager.set_password("managerPass123")

        self.cashier = User(
            restaurant_id=self.restaurant.id,
            name="KB Cashier",
            email="cashier@kacchi.com",
            phone="01711111103",
            role="cashier",
            is_active=True
        )
        self.cashier.set_password("cashierPass123")

        self.kitchen = User(
            restaurant_id=self.restaurant.id,
            name="KB Chef",
            email="kitchen@kacchi.com",
            phone="01711111104",
            role="kitchen",
            is_active=True
        )
        self.kitchen.set_password("kitchenPass123")

        # Seed Menu
        self.category = Category(restaurant_id=self.restaurant.id, name="Biryani", sort_order=1)
        db.session.add(self.category)
        db.session.commit()

        self.dish1 = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.category.id,
            name="Mutton Kacchi",
            price=Decimal("450.00"),
            discount=Decimal("0.00"),
            veg_type="non_veg",
            is_available=True,
            is_archived=False
        )
        self.dish2 = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.category.id,
            name="Borhani",
            price=Decimal("80.00"),
            discount=Decimal("10.00"),  # effective price: 70.00
            veg_type="veg",
            is_available=True,
            is_archived=False
        )
        self.dish_unavailable = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.category.id,
            name="Special Roast",
            price=Decimal("200.00"),
            discount=Decimal("0.00"),
            veg_type="non_veg",
            is_available=False,  # Sold out
            is_archived=False
        )
        self.dish_archived = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.category.id,
            name="Old Firni",
            price=Decimal("50.00"),
            discount=Decimal("0.00"),
            veg_type="veg",
            is_available=True,
            is_archived=True  # Archived
        )

        # Seed Floor: Space and Table (cover charge: ৳50)
        self.space = Space(restaurant_id=self.restaurant.id, name="AC Floor")
        db.session.add(self.space)
        db.session.commit()

        self.table = Table(
            restaurant_id=self.restaurant.id,
            space_id=self.space.id,
            name="T-10",
            capacity=4,
            cover_charge=Decimal("50.00"),
            status="open"
        )

        db.session.add_all([
            self.owner, self.manager, self.cashier, self.kitchen,
            self.dish1, self.dish2, self.dish_unavailable, self.dish_archived,
            self.table
        ])
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

    def test_terminal_access_and_role_gating(self):
        """Cashier, Manager, and Owner can access /pos/; Kitchen staff is blocked with 403."""
        # Cashier access
        self.login_as(self.cashier.email, "cashierPass123")
        res = self.client.get('/pos/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Mutton Kacchi", res.data)
        self.assertIn(b"Borhani", res.data)
        self.assertIn(b"Sold Out", res.data)
        self.assertNotIn(b"Old Firni", res.data)  # Archived dish must not appear

        # Kitchen access (blocked 403)
        self.login_as(self.kitchen.email, "kitchenPass123")
        res_kit = self.client.get('/pos/')
        self.assertEqual(res_kit.status_code, 403)

    def test_cart_htmx_interactions(self):
        """Adding dishes, stepping quantities, updating notes, and clearing cart."""
        self.login_as(self.cashier.email, "cashierPass123")

        # 1. Add Mutton Kacchi to cart
        res_add = self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.assertEqual(res_add.status_code, 200)
        self.assertIn(b"Mutton Kacchi", res_add.data)
        self.assertIn(b"450.00", res_add.data)

        # 2. Add Borhani (discounted: ৳70.00)
        res_add2 = self.client.post(f'/pos/cart/add/{self.dish2.id}')
        self.assertIn(b"Borhani", res_add2.data)
        self.assertIn(b"70.00", res_add2.data)

        # 3. Increment Mutton Kacchi (+1 -> qty 2)
        res_inc = self.client.post(f'/pos/cart/update-qty/{self.dish1.id}', data={'action': 'inc'})
        self.assertEqual(res_inc.status_code, 200)

        # 4. Update note on Borhani
        res_note = self.client.post(f'/pos/cart/update-note/{self.dish2.id}', data={'note': 'Chilled please'})
        self.assertEqual(res_note.status_code, 200)
        self.assertIn(b"Chilled please", res_note.data)

        # 5. Setting Order Type to Dine In with table
        res_type = self.client.post('/pos/cart/set-type', data={
            'order_type': 'dine_in',
            'table_id': self.table.id
        })
        self.assertIn(b"Table Cover Charge", res_type.data)
        self.assertIn(b"50.00", res_type.data)

        # 6. Clear cart
        res_clear = self.client.post('/pos/cart/clear')
        self.assertIn(b"Cart is Empty", res_clear.data)

    def test_place_order_and_price_recalculation(self):
        """Server strictly recalculates prices from DB; creates Order + OrderItems snapshots."""
        self.login_as(self.cashier.email, "cashierPass123")

        # Add 2 Mutton Kacchi (2 * 450 = 900) and 1 Borhani (effective 70)
        self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.client.post(f'/pos/cart/add/{self.dish2.id}')
        self.client.post(f'/pos/cart/update-note/{self.dish2.id}', data={'note': 'No ice'})

        # Place Quick Billing Order
        res_place = self.client.post('/pos/order/place', follow_redirects=True)
        self.assertEqual(res_place.status_code, 200)
        self.assertIn(b"Order #1 placed successfully!", res_place.data)

        order = Order.query.filter_by(restaurant_id=self.restaurant.id, order_no=1).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.type, 'quick')
        self.assertIsNone(order.table_id)
        self.assertEqual(order.status, 'open')

        # Financial verification (Subtotal: 980, Discount: 10, Net items: 970, VAT 5%: 48.50, Total: 1018.50)
        self.assertEqual(order.subtotal, Decimal('980.00'))
        self.assertEqual(order.discount, Decimal('10.00'))
        self.assertEqual(order.vat_amount, Decimal('48.50'))
        self.assertEqual(order.total, Decimal('1018.50'))

        # Verify OrderItems snapshots and kitchen status
        items = OrderItem.query.filter_by(order_id=order.id).all()
        self.assertEqual(len(items), 2)
        kacchi_item = next(i for i in items if i.dish_id == self.dish1.id)
        self.assertEqual(kacchi_item.dish_name_snapshot, "Mutton Kacchi")
        self.assertEqual(kacchi_item.unit_price_snapshot, Decimal("450.00"))
        self.assertEqual(kacchi_item.quantity, 2)
        self.assertEqual(kacchi_item.kitchen_status, 'new')

        borhani_item = next(i for i in items if i.dish_id == self.dish2.id)
        self.assertEqual(borhani_item.dish_name_snapshot, "Borhani")
        self.assertEqual(borhani_item.unit_price_snapshot, Decimal("70.00"))
        self.assertEqual(borhani_item.note, "No ice")
        self.assertEqual(borhani_item.kitchen_status, 'new')

    def test_dine_in_table_occupancy_transition(self):
        """Dine In order sets table status to occupied and applies cover charge."""
        self.login_as(self.cashier.email, "cashierPass123")

        # Set Dine In with table
        self.client.post('/pos/cart/set-type', data={
            'order_type': 'dine_in',
            'table_id': self.table.id
        })
        self.client.post(f'/pos/cart/add/{self.dish1.id}')

        res_place = self.client.post('/pos/order/place', follow_redirects=True)
        self.assertEqual(res_place.status_code, 200)

        # Verify Table is now Occupied
        db.session.refresh(self.table)
        self.assertEqual(self.table.status, 'occupied')

        order = Order.query.filter_by(table_id=self.table.id, status='open').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.cover_charge, Decimal("50.00"))

    def test_append_items_to_open_dine_in_table(self):
        """Cashier can append additional items to an open Dine In order on a table."""
        self.login_as(self.cashier.email, "cashierPass123")

        # Initial order on table: 1 Mutton Kacchi
        self.client.post('/pos/cart/set-type', data={'order_type': 'dine_in', 'table_id': self.table.id})
        self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.client.post('/pos/order/place', follow_redirects=True)

        initial_order = Order.query.filter_by(table_id=self.table.id, status='open').first()
        initial_total = initial_order.total

        # Round 2: Add 2 Borhani to the same table
        self.client.post('/pos/cart/set-type', data={'order_type': 'dine_in', 'table_id': self.table.id})
        self.client.post(f'/pos/cart/add/{self.dish2.id}')
        self.client.post(f'/pos/cart/add/{self.dish2.id}')

        res_append = self.client.post('/pos/order/place', follow_redirects=True)
        self.assertEqual(res_append.status_code, 200)
        self.assertIn(b"updated! Appended", res_append.data)

        # Same order has grown with updated total and new item
        db.session.refresh(initial_order)
        self.assertGreater(initial_order.total, initial_total)

        items = OrderItem.query.filter_by(order_id=initial_order.id).all()
        self.assertEqual(len(items), 2)  # 1 Kacchi item + 1 Borhani item (qty 2)

    def test_orders_directory_filtering_and_pagination(self):
        """Orders directory supports search by order #, status, and detail view."""
        self.login_as(self.cashier.email, "cashierPass123")

        # Create order #1
        self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.client.post('/pos/order/place')

        res_list = self.client.get('/pos/orders')
        self.assertEqual(res_list.status_code, 200)
        self.assertIn(b"#1", res_list.data)

        # Search query by order no
        res_search = self.client.get('/pos/orders?q=1')
        self.assertEqual(res_search.status_code, 200)
        self.assertIn(b"#1", res_search.data)

        # Detail view
        order = Order.query.filter_by(order_no=1).first()
        res_detail = self.client.get(f'/pos/orders/{order.id}')
        self.assertEqual(res_detail.status_code, 200)
        self.assertIn(b"Mutton Kacchi", res_detail.data)

    def test_order_cancellation_permissions_and_invariants(self):
        """Cashier blocked from cancelling; Manager/Owner can cancel with reason; releases table."""
        # 1. Place a Dine In order
        self.login_as(self.cashier.email, "cashierPass123")
        self.client.post('/pos/cart/set-type', data={'order_type': 'dine_in', 'table_id': self.table.id})
        self.client.post(f'/pos/cart/add/{self.dish1.id}')
        self.client.post('/pos/order/place')

        order = Order.query.filter_by(table_id=self.table.id, status='open').first()
        self.assertEqual(self.table.status, 'occupied')

        # 2. Cashier tries to cancel (Blocked 403 Forbidden)
        res_cancel_cashier = self.client.post(f'/pos/orders/{order.id}/cancel', data={
            'reason': 'Guest changed mind'
        })
        self.assertEqual(res_cancel_cashier.status_code, 403)

        # 3. Manager cancels order with valid reason
        self.login_as(self.manager.email, "managerPass123")
        res_cancel_mgr = self.client.post(f'/pos/orders/{order.id}/cancel', data={
            'reason': 'Customer left without dining'
        }, follow_redirects=True)
        self.assertEqual(res_cancel_mgr.status_code, 200)

        # Order is marked cancelled
        db.session.refresh(order)
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.cancel_reason, 'Customer left without dining')

        # Table is automatically released back to Open
        db.session.refresh(self.table)
        self.assertEqual(self.table.status, 'open')

        # AuditLog entry created
        audit = AuditLog.query.filter_by(action='ORDER_CANCELLED', record_id=order.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details['reason'], 'Customer left without dining')

if __name__ == '__main__':
    unittest.main()

