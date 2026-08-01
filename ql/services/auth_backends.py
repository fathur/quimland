from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from ql.models.user_property import UserProperty
from .utils import normalize_phone


class PhoneOrUsernameBackend(ModelBackend):
    """Same as ModelBackend, but 'username' may also be a UserProperty.phone."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if username is None or password is None:
            return None

        user = self._get_user_by_username(username) or self._get_user_by_phone(username)
        # user = self._get_user_by_phone(username)
        if user is None:
            # Hash anyway so a missing username/phone takes the same time as a wrong password.
            get_user_model()().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def _get_user_by_username(self, username):
        user_model = get_user_model()
        try:
            return user_model._default_manager.get_by_natural_key(username)
        except user_model.DoesNotExist:
            return None

    def _get_user_by_phone(self, raw):
        normalized = normalize_phone(raw)
        if not normalized:
            return None
        try:
            return UserProperty.objects.select_related('user').get(phone=normalized).user
        except (UserProperty.DoesNotExist, UserProperty.MultipleObjectsReturned):
            return None


class PhoneOrUsernameAuthForm(AdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Mobile Phone'
