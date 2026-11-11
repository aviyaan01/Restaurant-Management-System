from datetime import date
from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, StringField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional, Length

FINANCE_TYPE_CHOICES = [
    ('expense', 'Operational Expense (Utilities, Rent, Wages, etc.)'),
    ('purchase', 'Raw Materials / Market Purchase (Kitchen Inventory)'),
    ('sale', 'Manual Direct Sale / Other Revenue')
]

FINANCE_FILTER_TYPE_CHOICES = [
    ('all', 'All Transaction Types'),
    ('sale', 'Sales & Revenue'),
    ('purchase', 'Market Purchases'),
    ('expense', 'Operational Expenses')
]

class FinanceEntryForm(FlaskForm):
    """
    Form for manual financial cashbook entry.
    Used by Restaurant Owners and Managers for recording petty-cash purchases,
    operational expenses, and manual sales adjustments.
    """
    type = SelectField(
        'Transaction Type',
        choices=FINANCE_TYPE_CHOICES,
        default='expense',
        validators=[DataRequired(message="Please select a transaction type.")]
    )
    amount = DecimalField(
        'Amount (৳ BDT)',
        places=2,
        validators=[
            DataRequired(message="Amount is required."),
            NumberRange(min=0.01, message="Amount must be greater than zero.")
        ]
    )
    entry_date = DateField(
        'Transaction Date',
        default=date.today,
        validators=[DataRequired(message="Transaction date is required.")]
    )
    note = TextAreaField(
        'Description / Note',
        validators=[
            Optional(),
            Length(max=500, message="Note cannot exceed 500 characters.")
        ]
    )
    submit = SubmitField('Save Entry')

class FinanceFilterForm(FlaskForm):
    """
    Form for filtering the financial cashbook ledger by type and date range.
    """
    type = SelectField(
        'Type',
        choices=FINANCE_FILTER_TYPE_CHOICES,
        default='all',
        validators=[Optional()]
    )
    start_date = DateField(
        'From Date',
        validators=[Optional()]
    )
    end_date = DateField(
        'To Date',
        validators=[Optional()]
    )
    submit = SubmitField('Filter Records')

