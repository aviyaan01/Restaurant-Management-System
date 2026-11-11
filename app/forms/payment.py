from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional, Length

PAYMENT_METHOD_CHOICES = [
    ('cash', '💵 Cash'),
    ('bkash', '📱 bKash'),
    ('nagad', '📱 Nagad'),
    ('card', '💳 Card (Debit / Credit)')
]

class PaymentForm(FlaskForm):
    """
    Form for recording manual customer payments.
    Supports Cash, bKash, Nagad, and Card.
    Supports split payments and change due calculation.
    """
    method = SelectField(
        'Payment Method',
        choices=PAYMENT_METHOD_CHOICES,
        default='cash',
        validators=[DataRequired(message="Please select a payment method.")]
    )
    amount = DecimalField(
        'Amount to Pay (৳ BDT)',
        places=2,
        validators=[
            DataRequired(message="Payment amount is required."),
            NumberRange(min=0.01, message="Payment amount must be greater than zero.")
        ]
    )
    reference = StringField(
        'Transaction Reference / TrxID (Optional)',
        validators=[
            Optional(),
            Length(max=100, message="Reference cannot exceed 100 characters.")
        ]
    )
    cash_received = DecimalField(
        'Cash Tendered / Received (৳ BDT)',
        places=2,
        validators=[
            Optional(),
            NumberRange(min=0.00, message="Cash received cannot be negative.")
        ]
    )
    submit = SubmitField('Confirm Payment')

