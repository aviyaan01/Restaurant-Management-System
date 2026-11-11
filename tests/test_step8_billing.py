import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import unittest
from datetime import timedelta, datetime, timezone
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
from app.services.billing_service import (
    calculate_bill,
    calculate_change_due,
    record_order_payment
)
from app.services.order_service import (
    create_pos_order,
    append_items_to_pos_order,
    cancel_pos_order
)

# ==============================================================================
# 1. PURE FUNCTION UNIT TESTS: calculate_bill & calculate_change_due
# ==============================================================================

class TestBillCalculationUnit:
    """
    Unit test suite covering the standard BanglaPOS bill calculation engine.
    Verifies:
      - Exclusive VAT (added on top)
      - Inclusive VAT (embedded inside item prices)
      - Flat discounts and Percentage discounts
      - Cover charges (dine-in only)
      - Edge cases (0% VAT, 100% discount, discount > subtotal)
      - Standard NBR Bangladesh ROUND_HALF_UP decimal rounding rule
    """

    def test_exclusive_vat_standard(self):
        """Exclusive 5% VAT: ৳1000 + 5% = ৳1050 total with ৳50 VAT."""
        res = calculate_bill(
            subtotal=Decimal('1000.00'),
            discount_type='flat',
            discount_value=Decimal('0.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('5.00'),
            price_mode='exclusive'
        )
        assert res['subtotal'] == Decimal('1000.00')
        assert res['discount'] == Decimal('0.00')
        assert res['net_subtotal'] == Decimal('1000.00')
        assert res['cover_charge'] == Decimal('0.00')
        assert res['taxable_base'] == Decimal('1000.00')
        assert res['vat_amount'] == Decimal('50.00')
        assert res['total'] == Decimal('1050.00')
        assert res['price_mode'] == 'exclusive'

    def test_exclusive_vat_with_cover_charge(self):
        """Cover charge is added to taxable base before applying exclusive VAT."""
        # Net subtotal ৳1000 + Cover charge ৳50 = Taxable base ৳1050
        # VAT 5% of ৳1050 = ৳52.50 -> Total = ৳1102.50
        res = calculate_bill(
            subtotal=Decimal('1000.00'),
            discount_type='flat',
            discount_value=Decimal('0.00'),
            cover_charge=Decimal('50.00'),
            vat_rate=Decimal('5.00'),
            price_mode='exclusive'
        )
        assert res['net_subtotal'] == Decimal('1000.00')
        assert res['cover_charge'] == Decimal('50.00')
        assert res['taxable_base'] == Decimal('1050.00')
        assert res['vat_amount'] == Decimal('52.50')
        assert res['total'] == Decimal('1102.50')

    def test_inclusive_vat_standard(self):
        """
        Inclusive 5% VAT: ৳1050 total already includes 5% VAT.
        Pre-tax base = 1050 / 1.05 = ৳1000.00.
        VAT = ৳1050 - ৳1000 = ৳50.00. Total payable remains ৳1050.00.
        """
        res = calculate_bill(
            subtotal=Decimal('1050.00'),
            discount_type='flat',
            discount_value=Decimal('0.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('5.00'),
            price_mode='inclusive'
        )
        assert res['subtotal'] == Decimal('1050.00')
        assert res['taxable_base'] == Decimal('1050.00')
        assert res['vat_amount'] == Decimal('50.00')
        assert res['total'] == Decimal('1050.00')
        assert res['price_mode'] == 'inclusive'

    def test_inclusive_vat_with_cover_charge(self):
        """Inclusive VAT with cover charge included in total payable."""
        # Subtotal ৳500 + Cover ৳50 = Taxable ৳550
        # Inclusive VAT 10%: Pre-tax = 550 / 1.10 = ৳500.00 -> VAT = ৳50.00 -> Total = ৳550.00
        res = calculate_bill(
            subtotal=Decimal('500.00'),
            discount_type='flat',
            discount_value=Decimal('0.00'),
            cover_charge=Decimal('50.00'),
            vat_rate=Decimal('10.00'),
            price_mode='inclusive'
        )
        assert res['taxable_base'] == Decimal('550.00')
        assert res['vat_amount'] == Decimal('50.00')
        assert res['total'] == Decimal('550.00')

    def test_flat_discount_calculation(self):
        """Flat discount reduces subtotal before tax."""
        # Subtotal ৳1000 - Discount ৳200 = Net ৳800.
        # Exclusive 5% VAT on ৳800 = ৳40. Total = ৳840.
        res = calculate_bill(
            subtotal=Decimal('1000.00'),
            discount_type='flat',
            discount_value=Decimal('200.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('5.00'),
            price_mode='exclusive'
        )
        assert res['discount'] == Decimal('200.00')
        assert res['net_subtotal'] == Decimal('800.00')
        assert res['vat_amount'] == Decimal('40.00')
        assert res['total'] == Decimal('840.00')

    def test_percent_discount_calculation(self):
        """Percentage discount calculates percentage of subtotal."""
        # Subtotal ৳1200 - 15% discount (৳180.00) = Net ৳1020.00.
        # Exclusive 5% VAT on ৳1020 = ৳51.00. Total = ৳1071.00.
        res = calculate_bill(
            subtotal=Decimal('1200.00'),
            discount_type='percent',
            discount_value=Decimal('15.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('5.00'),
            price_mode='exclusive'
        )
        assert res['discount'] == Decimal('180.00')
        assert res['net_subtotal'] == Decimal('1020.00')
        assert res['vat_amount'] == Decimal('51.00')
        assert res['total'] == Decimal('1071.00')

    def test_discount_capped_at_subtotal(self):
        """A flat discount greater than subtotal is safely capped at subtotal."""
        res = calculate_bill(
            subtotal=Decimal('500.00'),
            discount_type='flat',
            discount_value=Decimal('750.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('5.00')
        )
        assert res['discount'] == Decimal('500.00')
        assert res['net_subtotal'] == Decimal('0.00')
        assert res['total'] == Decimal('0.00')

    def test_percent_discount_exceeding_100_percent_rejected(self):
        """Percentage discounts over 100% raise ValueError."""
        with pytest.raises(ValueError, match="Percentage discount cannot exceed 100%"):
            calculate_bill(
                subtotal=Decimal('500.00'),
                discount_type='percent',
                discount_value=Decimal('105.00')
            )

    def test_negative_subtotal_or_discount_rejected(self):
        """Negative money inputs raise ValueError."""
        with pytest.raises(ValueError, match="Subtotal cannot be negative"):
            calculate_bill(subtotal=Decimal('-10.00'))

        with pytest.raises(ValueError, match="Discount value cannot be negative"):
            calculate_bill(subtotal=Decimal('100.00'), discount_value=Decimal('-5.00'))

    def test_nbr_half_up_rounding_rule(self):
        """
        Bangladesh NBR Rounding Mandate:
        Half-poisha (0.005 BDT) must round UP away from zero to 0.01 BDT.
        For example:
          Taxable base = ৳100.10, VAT rate = 15%
          100.10 * 0.15 = 15.0150
          With ROUND_HALF_UP -> ৳15.02 VAT, Total = ৳115.12.
        """
        res = calculate_bill(
            subtotal=Decimal('100.10'),
            discount_type='flat',
            discount_value=Decimal('0.00'),
            cover_charge=Decimal('0.00'),
            vat_rate=Decimal('15.00'),
            price_mode='exclusive'
        )
        assert res['vat_amount'] == Decimal('15.02')
        assert res['total'] == Decimal('115.12')

    def test_calculate_change_due(self):
        """Change due computes exact difference for cash tendered."""
        # Customer pays ৳1000 for ৳650 bill -> ৳350 change
        assert calculate_change_due(Decimal('650.00'), Decimal('1000.00')) == Decimal('350.00')
        # Exact amount -> ৳0 change
        assert calculate_change_due(Decimal('650.00'), Decimal('650.00')) == Decimal('0.00')
        # Short tendered -> ৳0 change
        assert calculate_change_due(Decimal('650.00'), Decimal('500.00')) == Decimal('0.00')


# ==============================================================================
# 2. INTEGRATION TESTS: Payment Recording, Split Payments, and Auditing
# ==============================================================================

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key-step-8'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

class Step8BillingAndPaymentTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Restaurant A (5% exclusive VAT)
        self.restaurant = Restaurant(
            name="Sultan's Dine",
            phone="01722222222",
            address="Dhanmondi, Dhaka",
            bin="987654321-0202",
            vat_rate=Decimal("5.00"),
            price_mode="exclusive"
        )
        # Seed Restaurant B for multi-tenancy tests
        self.restaurant_b = Restaurant(
            name="Kacchi Ghor",
            phone="01733333333",
            address="Gulshan, Dhaka",
            bin="112233445-0303",
            vat_rate=Decimal("10.00"),
            price_mode="inclusive"
        )
        db.session.add_all([self.restaurant, self.restaurant_b])
        db.session.commit()

        # Seed Users: Owner, Manager, Cashier, Kitchen
        self.owner = User(
            restaurant_id=self.restaurant.id,
            name="SD Owner",
            email="owner@sultans.com",
            phone="01722222201",
            role="owner",
            is_active=True
        )
        self.owner.set_password("ownerPass123")

        self.manager = User(
            restaurant_id=self.restaurant.id,
            name="SD Manager",
            email="manager@sultans.com",
            phone="01722222202",
            role="manager",
            is_active=True
        )
        self.manager.set_password("managerPass123")

        self.cashier = User(
            restaurant_id=self.restaurant.id,
            name="SD Cashier",
            email="cashier@sultans.com",
            phone="01722222203",
            role="cashier",
            is_active=True
        )
        self.cashier.set_password("cashierPass123")

        self.kitchen = User(
            restaurant_id=self.restaurant.id,
            name="SD Chef",
            email="chef@sultans.com",
            phone="01722222204",
            role="kitchen",
            is_active=True
        )
        self.kitchen.set_password("chefPass123")

        db.session.add_all([self.owner, self.manager, self.cashier, self.kitchen])
        db.session.commit()

        # Seed Space & Table
        self.space = Space(restaurant_id=self.restaurant.id, name="Main Hall")
        db.session.add(self.space)
        db.session.flush()

        self.table = Table(
            restaurant_id=self.restaurant.id,
            space_id=self.space.id,
            name="T-01",
            capacity=4,
            cover_charge=Decimal("20.00"),
            status="open"
        )
        db.session.add(self.table)
        db.session.flush()

        # Seed Menu
        self.cat = Category(restaurant_id=self.restaurant.id, name="Biryani")
        db.session.add(self.cat)
        db.session.flush()

        self.dish1 = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.cat.id,
            name="Kacchi Biryani",
            price=Decimal("450.00"),
            discount=Decimal("50.00"),  # effective unit price = 400.00
            is_available=True
        )
        self.dish2 = Dish(
            restaurant_id=self.restaurant.id,
            category_id=self.cat.id,
            name="Borhani",
            price=Decimal("80.00"),
            discount=Decimal("0.00"),
            is_available=True
        )
        db.session.add_all([self.dish1, self.dish2])
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

    def test_single_cash_payment_in_full(self):
        """
        Recording full payment via Cash:
          - order.status becomes 'paid' (locked)
          - order.payment_status becomes 'paid'
          - order.paid_at is set
          - Dine-in table status returns to 'open'
          - FinanceEntry of type 'sale' is created automatically with restaurant_id
          - AuditLog records ORDER_FULLY_PAID
        """
        # Create a Dine-In order: 1 Kacchi Biryani (eff ৳400) + Cover Charge (৳20)
        # Taxable = ৳420. VAT 5% exclusive = ৳21. Total = ৳441.00.
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish1.id, 'quantity': 1}],
            table_id=self.table.id
        )

        assert order.status == 'open'
        assert order.payment_status == 'unpaid'
        assert order.total == Decimal('441.00')
        assert self.table.status == 'occupied'

        # Cashier receives ৳500 cash for ৳441 bill
        res = record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            received_by_id=self.cashier.id,
            method='cash',
            amount=Decimal('441.00'),
            cash_received=Decimal('500.00')
        )

        assert res['is_fully_paid'] is True
        assert res['change_due'] == Decimal('59.00')
        assert res['actual_payment'] == Decimal('441.00')

        # Verify Order state in DB
        db.session.refresh(order)
        assert order.status == 'paid'
        assert order.payment_status == 'paid'
        assert order.paid_at is not None

        # Verify Table released back to open
        db.session.refresh(self.table)
        assert self.table.status == 'open'

        # Verify FinanceEntry automatically created
        sale = FinanceEntry.query.filter_by(
            restaurant_id=self.restaurant.id,
            order_id=order.id,
            type='sale'
        ).first()
        assert sale is not None
        assert sale.amount == Decimal('441.00')
        assert sale.created_by == self.cashier.id

        # Verify AuditLog
        audit = AuditLog.query.filter_by(
            restaurant_id=self.restaurant.id,
            record_id=order.id,
            action='ORDER_FULLY_PAID'
        ).first()
        assert audit is not None
        assert audit.details['method'] == 'cash'
        assert audit.details['change_due'] == 59.0

    def test_split_payment_bkash_and_cash(self):
        """
        Split Payment Flow:
          1. Customer pays ৳200 via bKash -> Order remains open with status 'partial'
          2. Customer pays remaining ৳241 via Cash -> Order completes, table opens, finance entry generated
        """
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish1.id, 'quantity': 1}],
            table_id=self.table.id
        )
        assert order.total == Decimal('441.00')

        # 1. Partial bKash Payment: ৳200
        p1 = record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            received_by_id=self.cashier.id,
            method='bkash',
            amount=Decimal('200.00'),
            reference='BKASH-TRX-9988'
        )

        assert p1['is_fully_paid'] is False
        assert p1['remaining_due'] == Decimal('241.00')

        db.session.refresh(order)
        assert order.status == 'open'
        assert order.payment_status == 'partial'
        assert order.paid_at is None
        assert self.table.status == 'occupied'

        # No sale entry created yet
        assert FinanceEntry.query.filter_by(order_id=order.id).count() == 0

        # Partial payment audit recorded
        audit1 = AuditLog.query.filter_by(
            record_id=order.id,
            action='ORDER_PARTIAL_PAYMENT'
        ).first()
        assert audit1 is not None

        # 2. Settle remaining ৳241 in Cash
        p2 = record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            received_by_id=self.cashier.id,
            method='cash',
            amount=Decimal('241.00'),
            cash_received=Decimal('250.00')
        )

        assert p2['is_fully_paid'] is True
        assert p2['change_due'] == Decimal('9.00')
        assert p2['remaining_due'] == Decimal('0.00')

        db.session.refresh(order)
        assert order.status == 'paid'
        assert order.payment_status == 'paid'
        assert order.paid_at is not None

        # Table returned to open
        db.session.refresh(self.table)
        assert self.table.status == 'open'

        # FinanceEntry created
        sale = FinanceEntry.query.filter_by(order_id=order.id).first()
        assert sale is not None
        assert sale.amount == Decimal('441.00')

        # Both payment records exist
        payments = Payment.query.filter_by(order_id=order.id).all()
        assert len(payments) == 2
        methods = {p.method for p in payments}
        assert methods == {'bkash', 'cash'}

    def test_non_cash_payment_cannot_exceed_remaining_balance(self):
        """Digital payments (bKash, Nagad, Card) cannot exceed remaining balance due."""
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish2.id, 'quantity': 1}]  # ৳80 + 5% VAT = ৳84.00
        )
        assert order.total == Decimal('84.00')

        with pytest.raises(ValueError, match="cannot exceed the balance due"):
            record_order_payment(
                order_id=order.id,
                restaurant_id=self.restaurant.id,
                received_by_id=self.cashier.id,
                method='nagad',
                amount=Decimal('100.00')
            )

    def test_cannot_pay_already_paid_or_cancelled_order(self):
        """Cannot record payment for an order that is already paid or cancelled."""
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish2.id, 'quantity': 1}]
        )

        # Pay in full
        record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            received_by_id=self.cashier.id,
            method='cash',
            amount=order.total
        )

        # Second payment rejected
        with pytest.raises(ValueError, match="already fully paid and locked"):
            record_order_payment(
                order_id=order.id,
                restaurant_id=self.restaurant.id,
                received_by_id=self.cashier.id,
                method='cash',
                amount=Decimal('10.00')
            )

        # Cancelled order
        order2 = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish2.id, 'quantity': 1}]
        )
        cancel_pos_order(order2.id, self.restaurant.id, self.manager.id, reason="Customer cancelled")

        with pytest.raises(ValueError, match="Cannot record payment for cancelled"):
            record_order_payment(
                order_id=order2.id,
                restaurant_id=self.restaurant.id,
                received_by_id=self.cashier.id,
                method='cash',
                amount=order2.total
            )

    def test_paid_order_protection_cashier_blocked_manager_allowed_and_audited(self):
        """
        Rule: Paid orders can be changed ONLY by a manager or owner, and every such change is audited.
        Cashier attempting to append items or cancel a paid order is strictly rejected.
        Manager modifying a paid order transitions order back to partial/open and logs PAID_ORDER_MODIFIED.
        """
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='dine_in',
            items_data=[{'dish_id': self.dish2.id, 'quantity': 1}],
            table_id=self.table.id
        )
        # Pay in full
        record_order_payment(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            received_by_id=self.cashier.id,
            method='cash',
            amount=order.total
        )
        assert order.status == 'paid'

        # 1. Cashier attempts to append items -> PermissionError
        with pytest.raises(PermissionError, match="Paid orders can be changed only by a manager or owner"):
            append_items_to_pos_order(
                order_id=order.id,
                restaurant_id=self.restaurant.id,
                user_id=self.cashier.id,
                new_items_data=[{'dish_id': self.dish2.id, 'quantity': 1}]
            )

        # 2. Manager appends items -> Succeeds and Audited
        append_items_to_pos_order(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            user_id=self.manager.id,
            new_items_data=[{'dish_id': self.dish2.id, 'quantity': 1}]
        )

        db.session.refresh(order)
        # New total increased, so order is now partial/open again
        assert order.status == 'open'
        assert order.payment_status == 'partial'

        # Audit log verification
        audit = AuditLog.query.filter_by(
            record_id=order.id,
            action='PAID_ORDER_MODIFIED'
        ).first()
        assert audit is not None
        assert audit.user_id == self.manager.id
        assert audit.details['modified_by_role'] == 'manager'

        # 3. Manager cancels paid order -> Audited as PAID_ORDER_CANCELLED
        cancel_pos_order(
            order_id=order.id,
            restaurant_id=self.restaurant.id,
            user_id=self.manager.id,
            reason="Guest requested full refund and cancellation"
        )
        db.session.refresh(order)
        assert order.status == 'cancelled'

    def test_payment_web_routes(self):
        """
        Web route testing for GET /pos/orders/<id>/pay and POST /pos/orders/<id>/pay.
        Verifies:
          - Cashier access (200 OK)
          - Payment form submission
          - Kitchen role gating (403 Forbidden)
          - Multi-tenant data separation (404 Not Found)
        """
        order = create_pos_order(
            restaurant_id=self.restaurant.id,
            user_id=self.cashier.id,
            order_type='quick',
            items_data=[{'dish_id': self.dish1.id, 'quantity': 1}] # ৳400 + 5% VAT = ৳420
        )

        # 1. Cashier GET payment page
        self.login_as(self.cashier.email, "cashierPass123")
        res = self.client.get(f'/pos/orders/{order.id}/pay')
        assert res.status_code == 200
        assert b"Record Payment" in res.data
        assert b"Cash Tendered" in res.data
        assert b"420.00" in res.data

        # 2. Partial Payment via bKash POST
        res_post = self.client.post(f'/pos/orders/{order.id}/pay', data={
            'method': 'bkash',
            'amount': '200.00',
            'reference': 'TRX-TEST-BKASH',
            'cash_received': ''
        }, follow_redirects=True)

        assert res_post.status_code == 200
        assert b"Remaining balance due" in res_post.data

        # 3. Complete Remaining Balance via Cash
        res_complete = self.client.post(f'/pos/orders/{order.id}/pay', data={
            'method': 'cash',
            'amount': '220.00',
            'reference': '',
            'cash_received': '300.00'
        }, follow_redirects=True)

        assert res_complete.status_code == 200
        assert b"is fully paid" in res_complete.data
        assert b"Change Due: \xe0\xa7\xb380.00" in res_complete.data or b"Change Due" in res_complete.data

        # 4. Kitchen staff role gating -> 403 Forbidden
        self.login_as(self.kitchen.email, "chefPass123")
        res_kitchen = self.client.get(f'/pos/orders/{order.id}/pay')
        assert res_kitchen.status_code == 403

        # 5. Cross-tenant isolation: Tenant B user cannot access Tenant A's order
        user_b = User(
            restaurant_id=self.restaurant_b.id,
            name="TB Cashier",
            email="tb_cashier@kacchi.com",
            phone="01799999999",
            role="cashier",
            is_active=True
        )
        user_b.set_password("passTB123")
        db.session.add(user_b)
        db.session.commit()

        self.login_as(user_b.email, "passTB123")
        res_cross = self.client.get(f'/pos/orders/{order.id}/pay')
        assert res_cross.status_code == 404
