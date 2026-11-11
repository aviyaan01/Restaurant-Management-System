from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, ValidationError, Optional

VEG_CHOICES = [
    ('non_veg', 'Non-Vegetarian (মাংস / মাছ)'),
    ('veg', 'Vegetarian (নিরামিষ / সবজি)'),
    ('egg', 'Contains Egg (ডিম)')
]

class CategoryForm(FlaskForm):
    """Form for creating and editing menu categories."""
    name = StringField('Category Name', validators=[
        DataRequired(message="Category name is required."),
        Length(min=2, max=100, message="Category name must be between 2 and 100 characters.")
    ])
    sort_order = IntegerField('Sort Order', default=0, validators=[
        NumberRange(min=0, message="Sort order must be 0 or a positive number.")
    ])
    submit = SubmitField('Save Category')

class DishForm(FlaskForm):
    """
    Form for creating and editing dishes.
    Enforces Rule 3 (BDT Numeric) and Rule 4 (Non-negative price, discount <= price).
    """
    name = StringField('Dish Name', validators=[
        DataRequired(message="Dish name is required."),
        Length(min=2, max=150, message="Dish name must be between 2 and 150 characters.")
    ])
    category_id = SelectField('Category', coerce=int, validators=[
        DataRequired(message="Please select a category for this dish.")
    ])
    price = DecimalField('Regular Price (৳ BDT)', places=2, validators=[
        DataRequired(message="Price is required."),
        NumberRange(min=0.00, message="Price cannot be negative.")
    ])
    discount = DecimalField('Discount (৳ BDT)', places=2, default=0.00, validators=[
        Optional(),
        NumberRange(min=0.00, message="Discount cannot be negative.")
    ])
    veg_type = SelectField('Dietary Classification', choices=VEG_CHOICES, default='non_veg', validators=[
        DataRequired(message="Please select a dietary classification.")
    ])
    prep_time_minutes = IntegerField('Preparation Time (Minutes)', default=15, validators=[
        DataRequired(message="Preparation time is required."),
        NumberRange(min=1, max=240, message="Preparation time must be between 1 and 240 minutes.")
    ])
    is_available = BooleanField('Available for Ordering', default=True)
    submit = SubmitField('Save Dish')

    def validate_discount(self, field):
        """Rule 4: Discount cannot exceed base price."""
        if self.price.data is not None and field.data is not None:
            if field.data > self.price.data:
                raise ValidationError("Discount (৳) cannot be greater than the regular price (৳).")

