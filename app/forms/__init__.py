from app.forms.auth import LoginForm
from app.forms.settings import RestaurantSettingsForm
from app.forms.staff import StaffCreateForm, StaffEditForm
from app.forms.menu import CategoryForm, DishForm
from app.forms.table import SpaceForm, TableForm, BulkTableForm
from app.forms.order import OrderCancelForm, OrderFilterForm
from app.forms.payment import PaymentForm

__all__ = [
    'LoginForm',
    'RestaurantSettingsForm',
    'StaffCreateForm',
    'StaffEditForm',
    'CategoryForm',
    'DishForm',
    'SpaceForm',
    'TableForm',
    'BulkTableForm',
    'OrderCancelForm',
    'OrderFilterForm',
    'PaymentForm',
]
