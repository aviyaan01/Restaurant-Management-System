from flask_wtf import FlaskForm
from wtforms import SelectField, DateField, SubmitField
from wtforms.validators import Optional

ACTION_CHOICES = [
    ('', 'All Recorded Actions'),
    ('ORDER_FULLY_PAID', 'Order Fully Paid'),
    ('ORDER_CANCELLED', 'Order Cancelled'),
    ('FINANCE_ENTRY_CREATED', 'Finance Entry Created'),
    ('FINANCE_ENTRY_UPDATED', 'Finance Entry Updated'),
    ('FINANCE_ENTRY_DELETED', 'Finance Entry Deleted'),
    ('STAFF_CREATED', 'Staff Member Created'),
    ('STAFF_EDITED', 'Staff Member Edited'),
    ('STAFF_STATUS_TOGGLED', 'Staff Status Toggled'),
    ('SETTINGS_UPDATED', 'Restaurant Settings Updated'),
    ('DISH_PRICE_CHANGED', 'Dish Price Changed'),
    ('DISH_AVAILABILITY_TOGGLED', 'Dish Availability Toggled'),
    ('DISH_ARCHIVED', 'Dish Archived'),
    ('TABLE_STATUS_CHANGED', 'Table Status Changed'),
    ('USER_LOGIN', 'User Login'),
    ('ACCOUNT_LOCKED', 'Account Lockout')
]

RECORD_TYPE_CHOICES = [
    ('', 'All Entity Types'),
    ('Order', 'Orders & Billing'),
    ('FinanceEntry', 'Finance Cashbook'),
    ('User', 'Staff & Users'),
    ('Dish', 'Menu Dishes'),
    ('Category', 'Menu Categories'),
    ('Space', 'Dining Spaces'),
    ('Table', 'Dining Tables'),
    ('Restaurant', 'Restaurant Profile')
]

class AuditFilterForm(FlaskForm):
    """
    Form for filtering immutable tenant audit logs by user, action, record type, and date range.
    """
    user_id = SelectField(
        'Staff Member',
        choices=[],
        default='',
        validators=[Optional()]
    )
    action = SelectField(
        'Action',
        choices=ACTION_CHOICES,
        default='',
        validators=[Optional()]
    )
    record_type = SelectField(
        'Entity Type',
        choices=RECORD_TYPE_CHOICES,
        default='',
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
    submit = SubmitField('Filter Logs')

