import re
from decimal import Decimal
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, DecimalField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, NumberRange, Optional
from app.models.user import User

class LoginForm(FlaskForm):
    """
    Login form supporting dual-identifier authentication (Email or Bangladeshi Phone).
    Server-side validation enforces non-empty input and a minimum 8-character password.
    """
    identifier = StringField('Email or Phone Number', validators=[
        DataRequired(message="Please provide your registered email or phone number."),
        Length(min=3, max=120, message="Identifier must be between 3 and 120 characters.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Please provide your password."),
        Length(min=8, message="Password must be at least 8 characters.")
    ])
    remember = BooleanField('Remember this device')
    submit = SubmitField('Sign In')

class RegisterForm(FlaskForm):
    """
    Self-service restaurant registration form.
    Creates a new Restaurant tenant and its primary Owner user account.
    """
    # --- Restaurant Details ---
    restaurant_name = StringField('Restaurant Name', validators=[
        DataRequired(message="Please enter your restaurant name."),
        Length(min=3, max=150, message="Restaurant name must be between 3 and 150 characters.")
    ])
    restaurant_phone = StringField('Restaurant Phone Number', validators=[
        DataRequired(message="Please enter your restaurant contact phone number."),
        Length(min=11, max=15, message="Phone number must be between 11 and 15 digits.")
    ])
    restaurant_address = StringField('Restaurant Address', validators=[
        Optional(),
        Length(max=255, message="Address cannot exceed 255 characters.")
    ])
    price_mode = SelectField(
        'VAT Calculation Mode',
        choices=[
            ('exclusive', 'Exclusive (VAT is added on top of menu prices)'),
            ('inclusive', 'Inclusive (Menu prices already include VAT)')
        ],
        default='exclusive',
        validators=[DataRequired()]
    )
    vat_rate = DecimalField(
        'Default VAT Rate (%)',
        default=Decimal('5.00'),
        places=2,
        validators=[
            DataRequired(message="Please specify the default VAT percentage."),
            NumberRange(min=0, max=100, message="VAT rate must be between 0% and 100%.")
        ]
    )

    # --- Owner Account Details ---
    owner_name = StringField('Owner Full Name', validators=[
        DataRequired(message="Please enter the owner's full name."),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters.")
    ])
    owner_email = StringField('Owner Email Address (for Login)', validators=[
        DataRequired(message="Please enter an email address for logging in."),
        Email(message="Please provide a valid email address."),
        Length(max=120)
    ])
    owner_phone = StringField('Owner Mobile Number (Optional)', validators=[
        Optional(),
        Length(min=11, max=15, message="Mobile number must be between 11 and 15 digits.")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Please enter a password."),
        Length(min=8, message="Password must be at least 8 characters.")
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(message="Please re-type your password to confirm."),
        EqualTo('password', message="Passwords do not match. Please re-enter.")
    ])
    submit = SubmitField('Create Restaurant & Account')

    def validate_restaurant_phone(self, field):
        cleaned = re.sub(r'[\s\-]', '', field.data or '')
        pattern = r'^(?:\+88|88)?(01[3-9]\d{8})$'
        if not re.match(pattern, cleaned):
            raise ValidationError("Please enter a valid 11-digit Bangladeshi mobile number (e.g., 01712345678).")

    def validate_owner_phone(self, field):
        if field.data:
            cleaned = re.sub(r'[\s\-]', '', field.data)
            pattern = r'^(?:\+88|88)?(01[3-9]\d{8})$'
            if not re.match(pattern, cleaned):
                raise ValidationError("Please enter a valid 11-digit Bangladeshi mobile number (e.g., 01712345678).")

    def validate_owner_email(self, field):
        email_clean = (field.data or '').strip().lower()
        if User.query.filter_by(email=email_clean).first():
            raise ValidationError("An account with this email address already exists. Please sign in or use a different email.")


