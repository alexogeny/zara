"""
The main goal of these mixins are to define most of what you need to get started.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from zara.utilities.database.validators import validate_slug, validate_username

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

    class User:
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

    class Session:
        pass


def dumb_datetime():
    return datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)


def id_field():
    return DatabaseField(
        auto_increment=False,
        primary_key=True,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
    )


class IdMixin:
    id: Required[str] = DatabaseField(
        auto_increment=False,
        primary_key=True,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
    )


class AuditMixin:
    id: Required[str] = DatabaseField(
        auto_increment=False,
        primary_key=True,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
    )

    created_at: Required[datetime.datetime] = DatabaseField(
        default=lambda: dumb_datetime(),
        data_type=datetime.datetime,
        nullable=False,
    )
    created_by: HasOne["User"] = HasOne["User"]
    updated_at: Optional[datetime.datetime] = None
    updated_by: HasOne["User"] = HasOne["User"]
    deleted_at: Optional[datetime.datetime] = None
    deleted_by: HasOne["User"] = HasOne["User"]


class SettingsMixin(AuditMixin):
    """Some basic settings to get started."""

    user: HasOne["User"] = HasOne["User"]
    display_mode: Optional[str] = Default("system")  # light, dark, system, hi contrast
    language: Optional[str] = DatabaseField(default="en", nullable=False)
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
    username: Required[str] = DatabaseField(
        unique=True, index=True, nullable=False, validate=validate_username
    )
    settings: HasOne["Settings"] = HasOne["Settings"]
    is_admin: Optional[bool] = DatabaseField(data_type=bool, default=False)
    is_system: Optional[bool] = DatabaseField(data_type=bool, default=False)
    role: HasOne["Role"] = HasOne["Role"]
    openid_provider: HasOne["OpenIDProvider"] = HasOne["OpenIDProvider"]
    openid_username: Optional[str] = DatabaseField(nullable=True)
    token_secret: Optional[str] = DatabaseField(
        auto_increment=False,
        primary_key=False,
        data_type=str,
        length=30,
        default=lambda: generate_lexicographical_uuid(),
        private=True,
    )
    sessions: HasMany["Session"] = HasMany["Session"]

    @property
    def is_active(self):
        now = dumb_datetime()
        return self.sessions.where(
            last_activity__isnull=False, revoked_at__isnull=True, expires_at__gt=now
        ).any()

    @property
    def last_login(self):
        now = dumb_datetime()

        return (
            self.sessions.where(last_activity__isnull=False, expires_at__gt=now)
            .sort_by("created_at")
            .last()
            .created_at
        )

    @property
    def last_activity(self):
        now = dumb_datetime()

        return (
            self.sessions.where(last_activity__isnull=False, expires_at__gt=now)
            .sort_by("last_activity")
            .last()
            .last_activity
        )


class SessionMixin(IdMixin):
    user: HasOne["User"] = HasOne["User"]
    access_token = DatabaseField(nullable=False)
    refresh_token = DatabaseField(nullable=False)
    expires_at: Optional[datetime.datetime] = DatabaseField(nullable=True)
    last_active: Optional[datetime.datetime] = DatabaseField(nullable=True)
    ip_address: Optional[str] = DatabaseField(nullable=True)
    revoked_at: Optional[datetime.datetime] = DatabaseField(nullable=True)
    user_agent: Optional[str] = DatabaseField(nullable=True)
    created_at: Required[datetime.datetime] = DatabaseField(
        default=lambda: dumb_datetime(),
        data_type=datetime.datetime,
        nullable=False,
    )


class RoleMixin(AuditMixin):
    """Role-based access control that has a defined subset of permissions."""

    name: Required[str] = DatabaseField(nullable=False)
    slug: Required[str] = DatabaseField(validate=validate_slug)
    is_custom: Optional[bool] = DatabaseField(data_type=bool, default=False)
    description: Required[str] = DatabaseField(nullable=False, data_type=str)
    role_permissions: HasMany["RolePermission"] = HasMany["RolePermission"]


class PermissionMixin(AuditMixin):
    """Permissions that form part of role-based access."""

    name: Required[str] = DatabaseField(nullable=False)
    slug: Required[str] = DatabaseField(validate=validate_slug)
    is_custom: Optional[bool] = DatabaseField(data_type=bool, default=False)
    description: Required[str] = DatabaseField(nullable=False, data_type=str)
    role_permissions: HasMany["RolePermission"] = HasMany["RolePermission"]


class RolePermissionMixin(AuditMixin):
    """Map table for linking roles and permissions."""

    role: HasOne["Role"] = HasOne["Role"]
    permission: HasOne["Permission"] = HasOne["Permission"]
