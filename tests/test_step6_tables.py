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
from app.models.table import Space, Table
from app.models.order import Order
from app.models.audit import AuditLog
from app.services.table_service import set_table_status, can_delete_table, can_delete_space

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-6'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step6TablesAndSpacesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant
        self.restaurant = Restaurant(
            name="Sultan's Dine",
            phone="01710000000",
            address="Dhanmondi, Dhaka",
            bin="998877665-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        db.session.add(self.restaurant)
        db.session.commit()

        # Seed Users: Owner, Manager, Cashier, Kitchen
        self.owner = User(
            restaurant_id=self.restaurant.id,
            name="Sultan Owner",
            email="owner@sultan.com",
            phone="01710000001",
            role="owner",
            is_active=True
        )
        self.owner.set_password("ownerPass123")

        self.manager = User(
            restaurant_id=self.restaurant.id,
            name="Sultan Manager",
            email="manager@sultan.com",
            phone="01710000002",
            role="manager",
            is_active=True
        )
        self.manager.set_password("managerPass123")

        self.cashier = User(
            restaurant_id=self.restaurant.id,
            name="Sultan Cashier",
            email="cashier@sultan.com",
            phone="01710000003",
            role="cashier",
            is_active=True
        )
        self.cashier.set_password("cashierPass123")

        self.kitchen = User(
            restaurant_id=self.restaurant.id,
            name="Sultan Chef",
            email="kitchen@sultan.com",
            phone="01710000004",
            role="kitchen",
            is_active=True
        )
        self.kitchen.set_password("kitchenPass123")

        db.session.add_all([self.owner, self.manager, self.cashier, self.kitchen])
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

    def test_space_crud_and_duplicate_guard(self):
        """Owner and Manager can create, edit, and list dining spaces."""
        self.login_as(self.manager.email, "managerPass123")

        # 1. Create Space
        res_create = self.client.post('/admin/spaces/new', data={
            'name': 'Ground Floor'
        }, follow_redirects=True)
        self.assertEqual(res_create.status_code, 200)
        self.assertIn(b"Ground Floor", res_create.data)

        space = Space.query.filter_by(restaurant_id=self.restaurant.id, name="Ground Floor").first()
        self.assertIsNotNone(space)

        # 2. Prevent Duplicate Space Name in Same Restaurant
        res_dup = self.client.post('/admin/spaces/new', data={
            'name': 'Ground Floor'
        }, follow_redirects=True)
        self.assertEqual(res_dup.status_code, 200)
        self.assertIn(b"already exists in your restaurant", res_dup.data)

        # 3. Edit Space
        res_edit = self.client.post(f'/admin/spaces/{space.id}/edit', data={
            'name': 'Main Dining Hall'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"Main Dining Hall", res_edit.data)

        db.session.refresh(space)
        self.assertEqual(space.name, "Main Dining Hall")

        # 4. Delete Empty Space
        res_del = self.client.post(f'/admin/spaces/{space.id}/delete', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn(b"deleted successfully", res_del.data)
        self.assertIsNone(Space.query.filter_by(id=space.id).first())

    def test_table_crud_and_validations(self):
        """Table creation enforces capacity >= 1, non-negative cover charge, and uniqueness."""
        self.login_as(self.owner.email, "ownerPass123")

        space = Space(restaurant_id=self.restaurant.id, name="AC Hall")
        db.session.add(space)
        db.session.commit()

        # 1. Invalid Capacity (0 seats)
        res_invalid_cap = self.client.post('/admin/tables/new', data={
            'space_id': space.id,
            'name': 'T-01',
            'capacity': 0,
            'cover_charge': '0.00',
            'status': 'open'
        })
        self.assertIn(b"Capacity must be at least 1 guest", res_invalid_cap.data)

        # 2. Negative Cover Charge
        res_neg_cover = self.client.post('/admin/tables/new', data={
            'space_id': space.id,
            'name': 'T-01',
            'capacity': 4,
            'cover_charge': '-15.00',
            'status': 'open'
        })
        self.assertIn(b"Cover charge cannot be negative", res_neg_cover.data)

        # 3. Valid Table Creation
        res_create = self.client.post('/admin/tables/new', data={
            'space_id': space.id,
            'name': 'T-01',
            'capacity': 4,
            'cover_charge': '50.00',
            'status': 'open'
        }, follow_redirects=True)
        self.assertEqual(res_create.status_code, 200)
        self.assertIn(b"T-01", res_create.data)

        table = Table.query.filter_by(restaurant_id=self.restaurant.id, space_id=space.id, name="T-01").first()
        self.assertIsNotNone(table)
        self.assertEqual(table.capacity, 4)
        self.assertEqual(table.cover_charge, Decimal("50.00"))

        # 4. Duplicate Table Name in Same Space Rejected
        res_dup = self.client.post('/admin/tables/new', data={
            'space_id': space.id,
            'name': 'T-01',
            'capacity': 6,
            'cover_charge': '0.00',
            'status': 'open'
        })
        self.assertIn(b"already exists in this space", res_dup.data)

        # 5. Edit Table
        res_edit = self.client.post(f'/admin/tables/{table.id}/edit', data={
            'space_id': space.id,
            'name': 'T-01-VIP',
            'capacity': 8,
            'cover_charge': '100.00',
            'status': 'open'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        db.session.refresh(table)
        self.assertEqual(table.name, "T-01-VIP")
        self.assertEqual(table.capacity, 8)
        self.assertEqual(table.cover_charge, Decimal("100.00"))

    def test_bulk_table_creation(self):
        """Bulk table generator creates sequential tables (T1..T10) and handles skips."""
        self.login_as(self.manager.email, "managerPass123")

        space = Space(restaurant_id=self.restaurant.id, name="Rooftop")
        db.session.add(space)
        db.session.commit()

        # 1. Invalid Range: To < From
        res_invalid_range = self.client.post('/admin/tables/bulk', data={
            'space_id': space.id,
            'prefix': 'R-',
            'from_number': 10,
            'to_number': 5,
            'capacity': 4,
            'cover_charge': '0.00'
        })
        self.assertIn(b"Ending number (To) must be greater than or equal to starting number (From)", res_invalid_range.data)

        # 2. Exceeding Batch Limit (> 100)
        res_limit = self.client.post('/admin/tables/bulk', data={
            'space_id': space.id,
            'prefix': 'R-',
            'from_number': 1,
            'to_number': 150,
            'capacity': 4,
            'cover_charge': '0.00'
        })
        self.assertIn(b"Cannot generate more than 100 tables in a single batch", res_limit.data)

        # 3. Successful Bulk Generation (R-1 to R-5)
        res_bulk = self.client.post('/admin/tables/bulk', data={
            'space_id': space.id,
            'prefix': 'R-',
            'from_number': 1,
            'to_number': 5,
            'capacity': 4,
            'cover_charge': '0.00'
        }, follow_redirects=True)
        self.assertEqual(res_bulk.status_code, 200)
        self.assertIn(b"Successfully generated 5 tables", res_bulk.data)

        tables = Table.query.filter_by(space_id=space.id).order_by(Table.name.asc()).all()
        self.assertEqual(len(tables), 5)
        self.assertEqual([t.name for t in tables], ['R-1', 'R-2', 'R-3', 'R-4', 'R-5'])

        # 4. Partial Overlap: Bulk create R-3 to R-7 skips R-3, R-4, R-5 and adds R-6, R-7
        res_overlap = self.client.post('/admin/tables/bulk', data={
            'space_id': space.id,
            'prefix': 'R-',
            'from_number': 3,
            'to_number': 7,
            'capacity': 4,
            'cover_charge': '0.00'
        }, follow_redirects=True)
        self.assertEqual(res_overlap.status_code, 200)
        self.assertIn(b"Successfully generated 2 tables", res_overlap.data)
        self.assertIn(b"already existed and were skipped", res_overlap.data)

        total_tables = Table.query.filter_by(space_id=space.id).count()
        self.assertEqual(total_tables, 7)

    def test_set_table_status_service(self):
        """set_table_status() service switches table status and writes to AuditLog."""
        space = Space(restaurant_id=self.restaurant.id, name="Section A")
        table = Table(restaurant_id=self.restaurant.id, space=space, name="A-1", capacity=4, status='open')
        db.session.add_all([space, table])
        db.session.commit()

        # Transition to occupied
        updated_table = set_table_status(
            table_id=table.id,
            status='occupied',
            restaurant_id=self.restaurant.id,
            user_id=self.owner.id
        )
        self.assertEqual(updated_table.status, 'occupied')

        # Check AuditLog
        log_entry = AuditLog.query.filter_by(
            action='TABLE_STATUS_CHANGED',
            record_id=table.id,
            restaurant_id=self.restaurant.id
        ).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.details['old_status'], 'open')
        self.assertEqual(log_entry.details['new_status'], 'occupied')

        # Transition back to open
        set_table_status(
            table_id=table.id,
            status='open',
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id
        )
        db.session.refresh(table)
        self.assertEqual(table.status, 'open')

        # Invalid status rejection
        with self.assertRaises(ValueError):
            set_table_status(table.id, 'broken_status', self.restaurant.id)

        # Cross-tenant isolation (Rule 1)
        with self.assertRaises(ValueError):
            set_table_status(table.id, 'occupied', restaurant_id=999999)

    def test_table_and_space_delete_safety_invariants(self):
        """Prevent deleting occupied tables or tables with active open orders."""
        self.login_as(self.owner.email, "ownerPass123")

        space = Space(restaurant_id=self.restaurant.id, name="Lounge")
        table = Table(restaurant_id=self.restaurant.id, space=space, name="L-1", capacity=2, status='open')
        db.session.add_all([space, table])
        db.session.commit()

        # 1. Occupied table cannot be deleted
        table.status = 'occupied'
        db.session.commit()

        can_del, reason = can_delete_table(table.id, self.restaurant.id)
        self.assertFalse(can_del)
        self.assertIn("currently marked as occupied", reason)

        res_del_occ = self.client.post(f'/admin/tables/{table.id}/delete', follow_redirects=True)
        self.assertIn(b"currently marked as occupied", res_del_occ.data)

        # 2. Table with an open order cannot be deleted
        table.status = 'open'
        db.session.commit()

        order = Order(
            restaurant_id=self.restaurant.id,
            order_no=1001,
            type='dine_in',
            table_id=table.id,
            status='open',
            subtotal=Decimal('500.00'),
            total=Decimal('525.00')
        )
        db.session.add(order)
        db.session.commit()

        can_del_order, reason_order = can_delete_table(table.id, self.restaurant.id)
        self.assertFalse(can_del_order)
        self.assertIn("active open order", reason_order)

        res_del_order = self.client.post(f'/admin/tables/{table.id}/delete', follow_redirects=True)
        self.assertIn(b"active open order", res_del_order.data)

        # Space cannot be deleted if a table inside has open orders
        can_del_space, sp_reason = can_delete_space(space.id, self.restaurant.id)
        self.assertFalse(can_del_space)
        self.assertIn("has an open order", sp_reason)

        res_del_space = self.client.post(f'/admin/spaces/{space.id}/delete', follow_redirects=True)
        self.assertIn(b"has an open order", res_del_space.data)

        # 3. Once order is paid or cancelled, table can be deleted
        order.status = 'paid'
        db.session.commit()

        can_del_paid, _ = can_delete_table(table.id, self.restaurant.id)
        self.assertTrue(can_del_paid)

        res_del_ok = self.client.post(f'/admin/tables/{table.id}/delete', follow_redirects=True)
        self.assertIn(b"deleted successfully", res_del_ok.data)
        self.assertIsNone(Table.query.filter_by(id=table.id).first())

    def test_live_status_board_and_role_access(self):
        """Live table status board accessible by Owner, Manager, Cashier; blocked for Kitchen."""
        space = Space(restaurant_id=self.restaurant.id, name="Garden")
        table = Table(restaurant_id=self.restaurant.id, space=space, name="G-1", capacity=4, status='open')
        db.session.add_all([space, table])
        db.session.commit()

        # 1. Cashier can view board
        self.login_as(self.cashier.email, "cashierPass123")
        res_cashier = self.client.get('/admin/tables/board')
        self.assertEqual(res_cashier.status_code, 200)
        self.assertIn(b"Dining Floor &amp; Table Board", res_cashier.data)
        self.assertIn(b"G-1", res_cashier.data)

        # Cashier via /pos/tables redirects to board
        res_pos_tables = self.client.get('/pos/tables', follow_redirects=True)
        self.assertEqual(res_pos_tables.status_code, 200)
        self.assertIn(b"Dining Floor &amp; Table Board", res_pos_tables.data)

        # Cashier polling partial
        res_partial = self.client.get('/admin/tables/board/partial')
        self.assertEqual(res_partial.status_code, 200)
        self.assertIn(b"G-1", res_partial.data)

        # Cashier CANNOT access table CRUD routes (blocked 403)
        res_blocked_create = self.client.get('/admin/tables/new')
        self.assertEqual(res_blocked_create.status_code, 403)

        res_blocked_spaces = self.client.get('/admin/spaces')
        self.assertEqual(res_blocked_spaces.status_code, 403)

        # 2. Kitchen staff is blocked from table board (403)
        self.login_as(self.kitchen.email, "kitchenPass123")
        res_kitchen = self.client.get('/admin/tables/board')
        self.assertEqual(res_kitchen.status_code, 403)

    def test_htmx_status_toggle(self):
        """Cashier or Manager can toggle table status via HTMX."""
        space = Space(restaurant_id=self.restaurant.id, name="Balcony")
        table = Table(restaurant_id=self.restaurant.id, space=space, name="B-1", capacity=2, status='open')
        db.session.add_all([space, table])
        db.session.commit()

        self.login_as(self.cashier.email, "cashierPass123")

        # Toggle to occupied via HTMX header
        res_toggle = self.client.post(
            f'/admin/tables/{table.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        self.assertEqual(res_toggle.status_code, 200)
        self.assertIn(b"Occupied", res_toggle.data)

        db.session.refresh(table)
        self.assertEqual(table.status, 'occupied')

        # Toggle back to open
        res_toggle_back = self.client.post(
            f'/admin/tables/{table.id}/toggle-status',
            headers={'HX-Request': 'true'}
        )
        self.assertEqual(res_toggle_back.status_code, 200)
        self.assertIn(b"Open", res_toggle_back.data)

        db.session.refresh(table)
        self.assertEqual(table.status, 'open')

if __name__ == '__main__':
    unittest.main()
