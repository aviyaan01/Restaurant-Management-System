from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

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

