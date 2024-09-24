# Mixins

from zara.utilities.database.base import Model
from zara.utilities.database.mixins import (
    PermissionMixin,
    RoleMixin,
    RolePermissionMixin,
    SessionMixin,
    SettingsMixin,
    UsersMixin,
)


class User(Model, UsersMixin):
    pass


class Settings(Model, SettingsMixin):
    pass


class Role(Model, RoleMixin):
    pass


class Permission(Model, PermissionMixin):
    pass


class RolePermission(Model, RolePermissionMixin):
    pass


class Session(Model, SessionMixin):
    pass
