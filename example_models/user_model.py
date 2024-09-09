# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.fields import (
    HasMany,
)
from zara.utilities.database.mixins import (
    PermissionMixin,
    RoleMixin,
    SettingsMixin,
    UserMixin,
)


class User(Model, UserMixin):
    pets: HasMany["Pet"] = HasMany["Pet"]  # type: ignore  # noqa: F821


class Settings(Model, SettingsMixin):
    pass


class Role(Model, RoleMixin):
    pass


class Permission(Model, PermissionMixin):
    pass
