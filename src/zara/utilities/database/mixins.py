"""
The main goal of these mixins are to define most of what you need to get started.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from ..id57 import generate_lexicographical_uuid
from .fields import (
    DatabaseField,
    Default,
    HasMany,
    HasOne,
    Optional,
    Required,
)

if TYPE_CHECKING:

    class Users:
        pass

    class Settings:
        pass

    class Permission:
        pass

    class Role:
        pass

    class RolePermission:
        pass

    class OpenIDProvider:
        pass


class AuditMixin:
    id: Required[str] = DatabaseField(  # Base 57 timestamped uuid 4
        auto_increment=False,
        primary_key=True,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
    )

    created_at: Required[datetime.datetime] = DatabaseField(
        default=lambda: datetime.datetime.now(tz=datetime.timezone.utc).replace(
            tzinfo=None
        ),
        data_type=datetime.datetime,
        nullable=False,
    )
    created_by: HasOne["Users"] = HasOne["Users"]
    updated_at: Optional[datetime.datetime] = None
    updated_by: HasOne["Users"] = HasOne["Users"]
    deleted_at: Optional[datetime.datetime] = None
    deleted_by: HasOne["Users"] = HasOne["Users"]


class SettingsMixin(AuditMixin):
    """Some basic settings to get started."""

    user: HasOne["Users"] = HasOne["Users"]
    display_mode: Optional[str] = Default("system")  # light, dark, system, hi contrast
    language: Optional[str] = "a language code e.g. en_AU or de"
    theme: Optional[str] = "a theme, like blue or red"
    timezone: Optional[str] = "a timezone."
    reduced_motion: Optional[str] = Default("system")
    receive_email_notifications: Optional[bool] = Default(False)
    receive_text_notifications: Optional[bool] = Default(False)
    has_opted_out_of_marketing: Optional[bool] = Default(False)


class UsersMixin(AuditMixin):
    """Common properties you'd find on a user object."""

    password_hash: Optional[str] = DatabaseField(private=True)
    password_salt: Optional[str] = DatabaseField(private=True)
    recovery_codes: Optional[str] = DatabaseField(private=True)
    mfa_secret: Optional[str] = DatabaseField(private=True)
    email_address: Required[str] = DatabaseField(nullable=False)
    age: Optional[int] = DatabaseField(data_type=int, default=0)
    name: Required[str] = DatabaseField(nullable=False)
    username: Required[str] = DatabaseField(unique=True, index=True, nullable=False)
    # settings: HasOne["Settings"] = HasOne["Settings"]
    is_admin: Optional[bool] = DatabaseField(data_type=bool, default=False)
    is_system: Optional[bool] = DatabaseField(data_type=bool, default=False)
    # role: HasOne["Role"] = HasOne["Role"]
    # openid_provider: HasOne["OpenIDProvider"] = HasOne["OpenIDProvider"]


class SessionMixin:
    user: HasOne["Users"] = HasOne["Users"]
    access_token = None
    refresh_token = None
    expires_at: Optional[datetime.datetime] = None
    last_active: Optional[datetime.datetime] = None


class RoleMixin:
    """Role-based access control that has a defined subset of permissions."""

    name: Required[str] = None
    is_custom: Optional[bool] = Default(False)
    description: Required[str] = None
    role_permissions: HasMany["RolePermission"] = HasMany["RolePermission"]


class PermissionMixin:
    """Permissions that form part of role-based access."""

    name: Required[str] = None
    slug: Required[str] = None
    is_custom: Optional[bool] = Default(False)
    description: Required[str] = None
    role_permissions: HasMany["RolePermission"] = HasMany["RolePermission"]


class RolePermissionMixin:
    """Map table for linking roles and permissions."""

    role: HasOne["Role"] = HasOne["Role"]
    permission: HasOne["Permission"] = HasOne["Permission"]


class OpenIDProvidersMixin(AuditMixin):
    client_id: Required[str] = None
    client_secret: Required[str] = None
    redirect_uri: Optional[str] = None

    users: HasMany["Users"] = HasMany["Users"]
