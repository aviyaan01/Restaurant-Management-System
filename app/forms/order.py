from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField, DateField
from wtforms.validators import DataRequired, Length, Optional

class OrderCancelForm(FlaskForm):
    """
    Mandatory cancellation reason form for Managers and Owners.
    Enforces Rule 5 (AuditLog tracking) and operational accountability.
    """
    reason = TextAreaField('Cancellation Reason', validators=[
        DataRequired(message="Cancellation reason is mandatory."),
        Length(min=5, max=500, message="Reason must be between 5 and 500 characters.")
    ])
    submit = SubmitField('Confirm Cancellation')

class OrderFilterForm(FlaskForm):
    """Filter form for orders directory."""
    q = StringField('Search Order #', validators=[Optional()])
    status = SelectField('Status', choices=[
        ('', 'All Statuses'),
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], default='', validators=[Optional()])
    type = SelectField('Order Type', choices=[
        ('', 'All Types'),
        ('dine_in', 'Dine In'),
        ('take_away', 'Take Away'),
        ('quick', 'Quick Billing')
    ], default='', validators=[Optional()])
    staff_id = SelectField('Staff', coerce=int, validators=[Optional()])
    date = DateField('Date', format='%Y-%m-%d', validators=[Optional()])

