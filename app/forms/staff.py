from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

ROLE_CHOICES = [
    ('manager', 'Manager (Admin, Menu, Reports, POS)'),
    ('cashier', 'Cashier (POS Register & Billing)'),
    ('kitchen', 'Kitchen Staff (Kitchen Display System)'),
    ('owner', 'Co-Owner (Full Administrative Access)')
]

class StaffCreateForm(FlaskForm):
    """Form for onboarding a new staff user to the restaurant."""
    name = StringField('Full Name', validators=[
        DataRequired(message="Full name is required."),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters.")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Email address is required."),
        Email(message="Please provide a valid email address.", check_deliverability=False),
        Length(max=120)
    ])
    phone = StringField('Mobile Number (Optional)', validators=[
        Optional(),
        Length(min=6, max=30, message="Phone number must be between 6 and 30 characters.")
    ])
    role = SelectField('Staff Role', choices=ROLE_CHOICES, validators=[
        DataRequired(message="Please assign a role.")
    ])
    password = PasswordField('Initial Password', validators=[
        DataRequired(message="Password is required."),
        Length(min=8, message="Password must be at least 8 characters.")
    ])
    submit = SubmitField('Create Staff Member')

class StaffEditForm(FlaskForm):
    """Form for modifying an existing staff user's profile and permissions."""
    name = StringField('Full Name', validators=[
        DataRequired(message="Full name is required."),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters.")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Email address is required."),
        Email(message="Please provide a valid email address.", check_deliverability=False),
        Length(max=120)
    ])
    phone = StringField('Mobile Number (Optional)', validators=[
        Optional(),
        Length(min=6, max=30, message="Phone number must be between 6 and 30 characters.")
    ])
    role = SelectField('Staff Role', choices=ROLE_CHOICES, validators=[
        DataRequired(message="Please assign a role.")
    ])
    password = PasswordField('New Password (Leave blank to keep current)', validators=[
        Optional(),
        Length(min=8, message="New password must be at least 8 characters.")
    ])
    is_active = BooleanField('Account Active (Uncheck to immediately block system access)')
    submit = SubmitField('Update Staff Member')
