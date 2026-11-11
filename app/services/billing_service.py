from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from app.extensions import db
from app.models.order import Order
from app.models.payment import Payment
from app.models.finance import FinanceEntry
from app.models.user import User
from app.services.table_service import set_table_status
from app.utils.audit import log_audit

VALID_PAYMENT_METHODS = {'cash', 'bkash', 'nagad', 'card'}

def calculate_bill(
    subtotal: Decimal,
    discount_type: str = 'flat',
    discount_value: Decimal = Decimal('0.00'),
    cover_charge: Decimal = Decimal('0.00'),
    vat_rate: Decimal = Decimal('0.00'),
    price_mode: str = 'exclusive'
) -> dict:
    """
    Standard Bill Calculation Engine for Restaurant Management System (BanglaPOS).
    
    Calculation Flow:
      1. subtotal
      2. -> discount (flat ৳ or percentage %)
      3. -> net_subtotal
      4. -> cover charge (dine-in only)
      5. -> taxable_base
      6. -> VAT (using restaurant's vat_rate and price_mode)
      7. -> total payable
      
    Rounding Rule (Non-Negotiable Rule 3):
      All currency values are strictly manipulated as Python Decimal with 2 decimal places (100 poisha = 1 BDT).
      We use ROUND_HALF_UP (halfway values round away from zero: e.g. 0.005 -> 0.01, 0.004 -> 0.00).
      This is the standard financial rounding mandated by the National Board of Revenue (NBR) in Bangladesh,
      preventing penny-rounding drift across multi-item bills.
      
    Price Modes:
      - 'exclusive': VAT is added on top of taxable_base.
                     VAT = round(taxable_base * (vat_rate / 100), 2)
                     Total = taxable_base + VAT
      - 'inclusive': Menu prices already include VAT.
                     pre_tax_base = round(taxable_base / (1 + (vat_rate / 100)), 2)
                     VAT = taxable_base - pre_tax_base
                     Total = taxable_base
    """
    subtotal = Decimal(str(subtotal)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if subtotal < Decimal('0.00'):
        raise ValueError("Subtotal cannot be negative.")

    disc_val = Decimal(str(discount_value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if disc_val < Decimal('0.00'):
        raise ValueError("Discount value cannot be negative.")

    # 1. Discount calculation
    disc_type = (discount_type or 'flat').lower()
    if disc_type == 'percent':
        if disc_val > Decimal('100.00'):
            raise ValueError("Percentage discount cannot exceed 100%.")
        discount_amount = (subtotal * (disc_val / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        disc_type = 'flat'
        discount_amount = disc_val

    # Safety: discount cannot exceed subtotal
    discount_amount = max(Decimal('0.00'), min(discount_amount, subtotal))
    net_subtotal = (subtotal - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 2. Cover charge (dine in only)
    c_charge = max(Decimal('0.00'), Decimal(str(cover_charge))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    taxable_base = net_subtotal + c_charge

    # 3. VAT & Total calculation
    v_rate = max(Decimal('0.00'), Decimal(str(vat_rate))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    p_mode = (price_mode or 'exclusive').lower()
    if p_mode not in ('inclusive', 'exclusive'):
        p_mode = 'exclusive'

    if v_rate > Decimal('0.00'):
        if p_mode == 'inclusive':
            vat_factor = Decimal('1.00') + (v_rate / Decimal('100.00'))
            pre_tax_base = (taxable_base / vat_factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            vat_amount = taxable_base - pre_tax_base
            total = taxable_base
        else:
            vat_amount = (taxable_base * (v_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total = taxable_base + vat_amount
    else:
        vat_amount = Decimal('0.00')
        total = taxable_base

    return {
        'subtotal': subtotal,
        'discount': discount_amount,
        'discount_type': disc_type,
        'discount_value': disc_val,
        'discount_amount': discount_amount,
        'net_subtotal': net_subtotal,
        'cover_charge': c_charge,
        'taxable_base': taxable_base,
        'vat_rate': v_rate,
        'vat_amount': vat_amount.quantize(Decimal('0.01')),
        'total': total.quantize(Decimal('0.01')),
        'price_mode': p_mode
    }

def calculate_change_due(total_due: Decimal, cash_received: Decimal) -> Decimal:
    """Calculates cash change due. Returns 0.00 if cash received <= total due."""
    due = Decimal(str(total_due)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    received = Decimal(str(cash_received)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if received > due:
        return (received - due).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return Decimal('0.00')

def record_order_payment(
    order_id: int,
    restaurant_id: int,
    received_by_id: int,
    method: str,
    amount: Decimal,
    reference: str = None,
    cash_received: Decimal = None
) -> dict:
    """
    Records a payment transaction for an Order.
    Supports split payments across Cash, bKash, Nagad, and Card.
    
    When fully paid:
      - order.status = 'paid' (locked)
      - order.payment_status = 'paid'
      - order.paid_at set
      - Table returned to 'open' if dine-in
      - FinanceEntry of type 'sale' created automatically
      
    When partially paid:
      - order.status = 'open'
      - order.payment_status = 'partial'
    """
    order = Order.query.filter_by(id=order_id, restaurant_id=restaurant_id).first()
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.status == 'cancelled':
        raise ValueError(f"Cannot record payment for cancelled Order #{order.order_no}.")

    if order.status == 'paid' and order.payment_status == 'paid':
        raise ValueError(f"Order #{order.order_no} is already fully paid and locked.")

    clean_method = (method or '').lower().strip()
    if clean_method not in VALID_PAYMENT_METHODS:
        raise ValueError(f"Invalid payment method '{method}'. Must be one of: {VALID_PAYMENT_METHODS}")

    pay_amount = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if pay_amount <= Decimal('0.00'):
        raise ValueError("Payment amount must be greater than zero.")

    # Calculate already paid total
    already_paid = sum(
        Decimal(str(p.amount))
        for p in order.payments.all()
        if p.status == 'completed'
    )
    remaining_due = max(Decimal('0.00'), order.total - already_paid)

    if remaining_due <= Decimal('0.00'):
        raise ValueError(f"Order #{order.order_no} has no remaining balance due.")

    change_due = Decimal('0.00')
    actual_payment = pay_amount

    if clean_method == 'cash':
        if cash_received is not None:
            tendered = Decimal(str(cash_received)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if tendered < pay_amount:
                raise ValueError(f"Cash tendered (৳{tendered}) cannot be less than payment amount (৳{pay_amount}).")
            change_due = tendered - pay_amount
        elif pay_amount > remaining_due:
            # Cashier entered the tendered bill as amount (e.g. ৳1000 for ৳650 bill)
            tendered = pay_amount
            actual_payment = remaining_due
            change_due = tendered - actual_payment
    else:
        # Non-cash payments cannot exceed the remaining balance
        if pay_amount > remaining_due:
            raise ValueError(f"{clean_method.title()} payment (৳{pay_amount}) cannot exceed the balance due (৳{remaining_due}).")

    payment = Payment(
        restaurant_id=restaurant_id,
        order_id=order.id,
        method=clean_method,
        amount=actual_payment,
        status='completed',
        reference=(reference or '').strip() or None,
        received_by=received_by_id
    )
    db.session.add(payment)
    db.session.flush()

    new_total_paid = already_paid + actual_payment
    is_fully_paid = (new_total_paid >= order.total)

    if is_fully_paid:
        order.status = 'paid'
        order.payment_status = 'paid'
        order.paid_at = datetime.now(timezone.utc)

        # Release table back to open if Dine In
        if order.table_id:
            set_table_status(order.table_id, 'open', restaurant_id, received_by_id)

        # Non-negotiable Rule 5: Automatically create FinanceEntry of type 'sale'
        sale_entry = FinanceEntry(
            restaurant_id=restaurant_id,
            type='sale',
            amount=order.total,
            note=f"POS Order #{order.order_no} ({order.type}) - Paid in full via {clean_method.upper()}",
            entry_date=datetime.now(timezone.utc),
            order_id=order.id,
            created_by=received_by_id
        )
        db.session.add(sale_entry)

        log_audit(
            action='ORDER_FULLY_PAID',
            record_type='Order',
            record_id=order.id,
            details={
                'order_no': order.order_no,
                'method': clean_method,
                'final_payment': float(actual_payment),
                'total_paid': float(new_total_paid),
                'total_order': float(order.total),
                'change_due': float(change_due)
            },
            user_id=received_by_id,
            restaurant_id=restaurant_id
        )
    else:
        order.status = 'open'
        order.payment_status = 'partial'

        log_audit(
            action='ORDER_PARTIAL_PAYMENT',
            record_type='Order',
            record_id=order.id,
            details={
                'order_no': order.order_no,
                'method': clean_method,
                'payment_amount': float(actual_payment),
                'already_paid': float(new_total_paid),
                'remaining_due': float(order.total - new_total_paid)
            },
            user_id=received_by_id,
            restaurant_id=restaurant_id
        )

    db.session.commit()

    return {
        'payment': payment,
        'actual_payment': actual_payment,
        'change_due': change_due,
        'is_fully_paid': is_fully_paid,
        'total_paid': new_total_paid,
        'remaining_due': max(Decimal('0.00'), order.total - new_total_paid)
    }
