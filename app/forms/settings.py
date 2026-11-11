from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange

class RestaurantSettingsForm(FlaskForm):
    """
    Form for updating restaurant establishment details, BIN, VAT rates, and receipt formatting.
    Owner-only on the server.
    """
    name = StringField('Restaurant Name', validators=[
        DataRequired(message="Restaurant name is required."),
        Length(min=2, max=150, message="Name must be between 2 and 150 characters.")
    ])
    phone = StringField('Contact Phone Number', validators=[
        DataRequired(message="Phone number is required."),
        Length(min=6, max=30, message="Phone number must be between 6 and 30 characters.")
    ])
    address = TextAreaField('Physical Address', validators=[
        Length(max=500, message="Address must be under 500 characters.")
    ])
    bin = StringField('Business Identification Number (BIN)', validators=[
        Length(max=50, message="BIN must be under 50 characters.")
    ])
    vat_rate = DecimalField('VAT Rate (%)', places=2, validators=[
        DataRequired(message="VAT rate is required."),
        NumberRange(min=0.00, max=100.00, message="VAT rate must be between 0.00% and 100.00%.")
    ])
    price_mode = SelectField('Pricing & VAT Mode', choices=[
        ('exclusive', 'Exclusive (VAT is added on top of menu prices at billing)'),
        ('inclusive', 'Inclusive (Menu prices already include VAT)')
    ], validators=[DataRequired(message="Please select a pricing mode.")])
    receipt_footer = TextAreaField('Receipt Footer Message', validators=[
        Length(max=500, message="Footer message must be under 500 characters.")
    ])
    submit = SubmitField('Save Restaurant Settings')

