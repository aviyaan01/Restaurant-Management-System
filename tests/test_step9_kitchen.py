import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.menu import Category, Dish
from app.models.table import Space, Table
from app.models.order import Order, OrderItem
from app.models.audit import AuditLog
from app.services.order_service import create_pos_order
from app.services.kitchen_service import (
    get_active_kds_tickets,
    get_completed_kds_tickets,
    bump_ticket,
    bump_order_item,
    _calc_elapsed
)

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-9'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step9KitchenDisplayTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant A
        self.restaurant_a = Restaurant(
            name="Sultan's Dine",
            phone="01711111111",
            address="Dhanmondi, Dhaka",
            bin="112233445-0101",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        # Seed Restaurant B for multi-tenant isolation testing
        self.restaurant_b = Restaurant(
            name="Kacchi Bhai",
            phone="01722222222",
            address="Banani, Dhaka",
            bin="998877665-0202",
            vat_rate=Decimal("7.50"),
            price_mode="inclusive"
        )
        db.session.add_all([self.restaurant_a, self.restaurant_b])
        db.session.commit()

        # Seed Users for Restaurant A: Kitchen, Manager, Owner, Cashier
        self.chef_a = User(
            restaurant_id=self.restaurant_a.id,
            name="Chef Karim",
            email="chef@sultans.com",
            phone="01711111101",
            role="kitchen",
            is_active=True
        )
        self.chef_a.set_password("chefPass123")

        self.manager_a = User(
            restaurant_id=self.restaurant_a.id,
            name="Manager A",
            email="manager@sultans.com",
            phone="01711111102",
            role="manager",
            is_active=True
        )
        self.manager_a.set_password("managerPass123")

        self.owner_a = User(
            restaurant_id=self.restaurant_a.id,
            name="Owner A",
            email="owner@sultans.com",
            phone="01711111103",
            role="owner",
            is_active=True
        )
        self.owner_a.set_password("ownerPass123")

        self.cashier_a = User(
            restaurant_id=self.restaurant_a.id,
            name="Cashier A",
            email="cashier@sultans.com",
            phone="01711111104",
            role="cashier",
            is_active=True
        )
        self.cashier_a.set_password("cashierPass123")

        # Seed Kitchen User for Restaurant B
        self.chef_b = User(
            restaurant_id=self.restaurant_b.id,
            name="Chef Rahim",
            email="chef@kacchi.com",
            phone="01722222201",
            role="kitchen",
            is_active=True
        )
        self.chef_b.set_password("chefBPass123")

        db.session.add_all([self.chef_a, self.manager_a, self.owner_a, self.cashier_a, self.chef_b])
        db.session.commit()

        # Seed Dining Spaces & Tables
        self.space_a = Space(restaurant_id=self.restaurant_a.id, name="Ground Floor")
        db.session.add(self.space_a)
        db.session.flush()

        self.table_a = Table(
            restaurant_id=self.restaurant_a.id,
            space_id=self.space_a.id,
            name="T-01",
            capacity=4,
            cover_charge=Decimal("0.00"),
            status="open"
        )
        self.table_a2 = Table(
            restaurant_id=self.restaurant_a.id,
            space_id=self.space_a.id,
            name="T-02",
            capacity=6,
            cover_charge=Decimal("0.00"),
            status="open"
        )
        db.session.add_all([self.table_a, self.table_a2])

        # Seed Menu Dishes for Restaurant A
        self.cat_a = Category(restaurant_id=self.restaurant_a.id, name="Biryani")
        db.session.add(self.cat_a)
        db.session.flush()

        self.dish_a1 = Dish(
            restaurant_id=self.restaurant_a.id,
            category_id=self.cat_a.id,
            name="Mutton Kacchi",
            price=Decimal("450.00"),
            discount=Decimal("0.00"),
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

        # Seed Menu Dishes for Restaurant B
        self.cat_b = Category(restaurant_id=self.restaurant_b.id, name="Rice")
        db.session.add(self.cat_b)
        db.session.flush()

        self.dish_b1 = Dish(
            restaurant_id=self.restaurant_b.id,
            category_id=self.cat_b.id,
            name="Beef Tehari",
            price=Decimal("300.00"),
            discount=Decimal("0.00"),
            is_available=True
        )
        db.session.add_all([self.dish_a1, self.dish_a2, self.dish_b1])
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
    # 1. RBAC & ACCESS CONTROL
    # ==========================================================================

    def test_kds_role_gating(self):
        """
        KDS is accessible to Kitchen staff, Managers, and Owners.
        Cashier is blocked with 403 Forbidden.
        Unauthenticated requests redirect to /auth/login.
        """
        # 1. Kitchen staff -> 200 OK
        self.login_as(self.chef_a.email, "chefPass123")
        res = self.client.get('/kitchen/')
        assert res.status_code == 200
        assert b"Kitchen Display System" in res.data
        assert b"LIVE" in res.data

        # 2. Manager -> 200 OK
        self.login_as(self.manager_a.email, "managerPass123")
        res = self.client.get('/kitchen/')
        assert res.status_code == 200

        # 3. Owner -> 200 OK
        self.login_as(self.owner_a.email, "ownerPass123")
        res = self.client.get('/kitchen/')
        assert res.status_code == 200

        # 4. Cashier -> 403 Forbidden
        self.login_as(self.cashier_a.email, "cashierPass123")
        res = self.client.get('/kitchen/')
        assert res.status_code == 403

        # 5. Unauthenticated -> 302 Redirect to login
        self.client.get('/auth/logout')
        res = self.client.get('/kitchen/')
        assert res.status_code == 302
        assert "/auth/login" in res.headers['Location']

    # ==========================================================================
    # 2. CHRONOLOGICAL QUEUE & TICKET DETAILS
    # ==========================================================================

    def test_chronological_ordering_oldest_first(self):
        """
        Active kitchen tickets are ordered strictly OLDEST FIRST (created_at ASC)
        so kitchen cooks in FIFO order.
        """
        # Order 1 placed at T=0
        order1 = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish_a1.id, 'quantity': 2, 'note': 'Less oil'}],
            table_id=self.table_a.id
        )

        # Order 2 placed at T=+2 min
        order2 = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_a2.id, 'quantity': 3}],
            table_id=None
        )

        tickets = get_active_kds_tickets(self.restaurant_a.id)
        assert len(tickets) == 2
        # Order 1 must appear before Order 2
        assert tickets[0]['order_id'] == order1.id
        assert tickets[1]['order_id'] == order2.id
        assert tickets[0]['table_name'] == 'T-01'
        assert tickets[1]['order_type'] == 'take_away'
        assert tickets[0]['items'][0].note == 'Less oil'

    def test_urgency_tier_calculation(self):
        """
        Elapsed time calculates urgency tiers:
          - < 10 mins: 'normal'
          - 10 - 20 mins: 'warning'
          - >= 20 mins: 'urgent'
        """
        now = datetime.now(timezone.utc)
        # 5 mins ago
        _, m1, u1 = _calc_elapsed(now - timedelta(minutes=5))
        assert m1 == 5
        assert u1 == 'normal'

        # 12 mins ago
        _, m2, u2 = _calc_elapsed(now - timedelta(minutes=12))
        assert m2 == 12
        assert u2 == 'warning'

        # 25 mins ago
        _, m3, u3 = _calc_elapsed(now - timedelta(minutes=25))
        assert m3 == 25
        assert u3 == 'urgent'

    # ==========================================================================
    # 3. TICKET BUMPING: NEW -> PREPARING -> READY -> HISTORY
    # ==========================================================================

    def test_ticket_bumping_workflow(self):
        """
        Ticket Bumping Lifecycle:
          1. Initial order placed -> items are 'new', ticket is 'new'
          2. Bump ticket to 'preparing' -> all items become 'preparing'
          3. Bump individual item to 'ready' -> that item is 'ready'
          4. Bump entire ticket to 'ready' -> all items 'ready'
          5. Ticket automatically leaves the active queue and moves to history
          6. Actions are written to AuditLog
        """
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='dine_in',
            items_data=[
                {'dish_id': self.dish_a1.id, 'quantity': 1, 'note': 'Spicy'},
                {'dish_id': self.dish_a2.id, 'quantity': 2}
            ],
            table_id=self.table_a.id
        )

        # 1. Initially both items are 'new'
        active = get_active_kds_tickets(self.restaurant_a.id)
        assert len(active) == 1
        assert active[0]['ticket_status'] == 'new'
        assert active[0]['has_new'] is True

        # 2. Start preparing ticket
        bump_ticket(
            order_id=order.id,
            restaurant_id=self.restaurant_a.id,
            user_id=self.chef_a.id,
            target_status='preparing'
        )

        active = get_active_kds_tickets(self.restaurant_a.id)
        assert len(active) == 1
        assert active[0]['ticket_status'] == 'preparing'
        assert active[0]['has_new'] is False
        assert active[0]['is_all_preparing'] is True

        # Verify AuditLog
        audit_bump = AuditLog.query.filter_by(
            record_id=order.id,
            action='KDS_TICKET_BUMPED'
        ).first()
        assert audit_bump is not None
        assert audit_bump.details['target_status'] == 'preparing'

        # 3. Bump single item to 'ready'
        first_item = order.items.first()
        bump_order_item(
            item_id=first_item.id,
            restaurant_id=self.restaurant_a.id,
            user_id=self.chef_a.id,
            target_status='ready'
        )

        db.session.refresh(first_item)
        assert first_item.kitchen_status == 'ready'

        # Ticket is still in active queue because second item is still 'preparing'
        active = get_active_kds_tickets(self.restaurant_a.id)
        assert len(active) == 1
        assert active[0]['ready_count'] == 1

        # 4. Bump ticket to 'ready' (completes order)
        bump_ticket(
            order_id=order.id,
            restaurant_id=self.restaurant_a.id,
            user_id=self.chef_a.id,
            target_status='ready'
        )

        # 5. Ticket moves out of active queue
        active_after = get_active_kds_tickets(self.restaurant_a.id)
        assert len(active_after) == 0

        # 6. Ticket appears in Completed History
        completed = get_completed_kds_tickets(self.restaurant_a.id)
        assert len(completed) == 1
        assert completed[0]['order_id'] == order.id

    # ==========================================================================
    # 4. HTMX POLLING & WEB ROUTES
    # ==========================================================================

    def test_htmx_ticket_feed_polling_and_bumping_route(self):
        """
        Tests the /kitchen/tickets polling endpoint (polled every 2s)
        and POST /kitchen/tickets/<id>/bump HTMX endpoint.
        """
        self.login_as(self.chef_a.email, "chefPass123")

        # Create an order
        order = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish_a1.id, 'quantity': 1}]
        )

        # 1. Polling endpoint returns ticket card with order number
        res_feed = self.client.get('/kitchen/tickets')
        assert res_feed.status_code == 200
        assert f"#{order.order_no}".encode() in res_feed.data
        assert b"Mutton Kacchi" in res_feed.data
        assert b"Start Preparing" in res_feed.data

        # 2. POST bump ticket via HTMX
        res_bump = self.client.post(
            f'/kitchen/tickets/{order.id}/bump',
            data={'target_status': 'preparing'},
            headers={'HX-Request': 'true'}
        )
        assert res_bump.status_code == 200
        assert b"preparing" in res_bump.data.lower()

        # 3. Mark Ready via HTMX -> ticket leaves grid and returns empty state
        res_ready = self.client.post(
            f'/kitchen/tickets/{order.id}/bump',
            data={'target_status': 'ready'},
            headers={'HX-Request': 'true'}
        )
        assert res_ready.status_code == 200
        assert b"All Orders Bumped &amp; Clear!" in res_ready.data

        # 4. History tab route contains completed ticket
        res_history = self.client.get('/kitchen/?tab=history')
        assert res_history.status_code == 200
        assert f"#{order.order_no}".encode() in res_history.data
        assert b"Ready" in res_history.data

    # ==========================================================================
    # 5. MULTI-TENANCY DATA ISOLATION (NON-NEGOTIABLE RULE 1)
    # ==========================================================================

    def test_multi_restaurant_kds_data_isolation(self):
        """
        CRITICAL TEST: Ensures tickets NEVER leak between restaurants.
        Restaurant A has Order A1 & Order A2.
        Restaurant B has Order B1.
        Chef A sees ONLY Order A items, never Restaurant B items.
        Chef B sees ONLY Order B items, never Restaurant A items.
        Chef A cannot bump Chef B's ticket.
        """
        # Place order 1 for Restaurant A
        order_a = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish_a1.id, 'quantity': 1}],
            table_id=self.table_a.id
        )

        # Place order 2 for Restaurant A (order_no = 2)
        order_a2 = create_pos_order(
            restaurant_id=self.restaurant_a.id,
            user_id=self.manager_a.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_a2.id, 'quantity': 1}],
            table_id=None
        )

        # Place order for Restaurant B (order_no = 1)
        order_b = create_pos_order(
            restaurant_id=self.restaurant_b.id,
            user_id=self.chef_b.id,
            order_type='take_away',
            items_data=[{'dish_id': self.dish_b1.id, 'quantity': 1}],
            table_id=None
        )

        # 1. Chef A sees ONLY Restaurant A orders
        self.login_as(self.chef_a.email, "chefPass123")
        res_a = self.client.get('/kitchen/tickets')
        assert res_a.status_code == 200
        assert b"Mutton Kacchi" in res_a.data
        assert b"Special Borhani" in res_a.data
        assert b"#2" in res_a.data
        assert b"Beef Tehari" not in res_a.data

        # 2. Chef B sees ONLY Restaurant B orders
        self.login_as(self.chef_b.email, "chefBPass123")
        res_b = self.client.get('/kitchen/tickets')
        assert res_b.status_code == 200
        assert b"Beef Tehari" in res_b.data
        assert b"Mutton Kacchi" not in res_b.data
        assert b"Special Borhani" not in res_b.data
        # Restaurant A's order #2 must NOT appear in Restaurant B
        assert b"#2" not in res_b.data

        # 3. Chef A attempts to bump Chef B's order -> Rejected by restaurant_id filter
        with pytest.raises(ValueError, match="not found"):
            bump_ticket(
                order_id=order_b.id,
                restaurant_id=self.restaurant_a.id,
                user_id=self.chef_a.id,
                target_status='ready'
            )

        # Verify Restaurant B's order was NOT modified
        order_b_refreshed = db.session.get(Order, order_b.id)
        assert order_b_refreshed.items.first().kitchen_status == 'new'
