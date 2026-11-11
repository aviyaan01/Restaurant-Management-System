from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, SelectField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, ValidationError

STATUS_CHOICES = [
    ('open', 'Open (Available for Seating)'),
    ('occupied', 'Occupied (Dining in Progress)')
]

class SpaceForm(FlaskForm):
    """Form for creating and editing dining spaces/zones (e.g. Ground Floor, AC Hall, Rooftop)."""
    name = StringField('Space / Zone Name', validators=[
        DataRequired(message="Space name is required."),
        Length(min=2, max=100, message="Space name must be between 2 and 100 characters.")
    ])
    submit = SubmitField('Save Space')

class TableForm(FlaskForm):
    """
    Form for creating and editing an individual dining table.
    Enforces Rule 3 (BDT Numeric) and Rule 4 (positive capacity, non-negative cover charge).
    """
    space_id = SelectField('Dining Space / Zone', coerce=int, validators=[
        DataRequired(message="Please select a dining space.")
    ])
    name = StringField('Table Name / Code', validators=[
        DataRequired(message="Table name is required."),
        Length(min=1, max=50, message="Table name must be between 1 and 50 characters.")
    ])
    capacity = IntegerField('Seating Capacity (Guests)', default=4, validators=[
        InputRequired(message="Seating capacity is required."),
        NumberRange(min=1, max=100, message="Capacity must be at least 1 guest.")
    ])
    cover_charge = DecimalField('Cover Charge (৳ BDT)', places=2, default=0.00, validators=[
        Optional(),
        NumberRange(min=0.00, message="Cover charge cannot be negative.")
    ])
    status = SelectField('Initial Status', choices=STATUS_CHOICES, default='open', validators=[
        DataRequired(message="Please choose a status.")
    ])
    submit = SubmitField('Save Table')

class BulkTableForm(FlaskForm):
    """
    Form for generating multiple sequential tables in a space.
    Pattern: prefix + from_number + to_number (e.g. 'T', 1, 20 -> T1 through T20).
    """
    space_id = SelectField('Target Space / Zone', coerce=int, validators=[
        DataRequired(message="Please select a target dining space.")
    ])
    prefix = StringField('Table Prefix', default='T', validators=[
        DataRequired(message="Prefix is required (e.g. 'T', 'Table-', 'VIP-')."),
        Length(min=1, max=20, message="Prefix must be between 1 and 20 characters.")
    ])
    from_number = IntegerField('From Number', default=1, validators=[
        InputRequired(message="Starting table number is required."),
        NumberRange(min=1, max=9999, message="Starting number must be at least 1.")
    ])
    to_number = IntegerField('To Number', default=10, validators=[
        InputRequired(message="Ending table number is required."),
        NumberRange(min=1, max=9999, message="Ending number must be at least 1.")
    ])
    capacity = IntegerField('Seating Capacity per Table', default=4, validators=[
        InputRequired(message="Capacity is required."),
        NumberRange(min=1, max=100, message="Capacity must be at least 1 guest.")
    ])
    cover_charge = DecimalField('Cover Charge per Table (৳ BDT)', places=2, default=0.00, validators=[
        Optional(),
        NumberRange(min=0.00, message="Cover charge cannot be negative.")
    ])
    submit = SubmitField('Generate Tables')

    def validate_to_number(self, field):
        if self.from_number.data is not None and field.data is not None:
            if field.data < self.from_number.data:
                raise ValidationError("Ending number (To) must be greater than or equal to starting number (From).")
            if (field.data - self.from_number.data + 1) > 100:
                raise ValidationError("Cannot generate more than 100 tables in a single batch.")
