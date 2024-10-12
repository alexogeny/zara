# Example usage:
import datetime

from zara.utilities.database.orm import DatabaseField, Relationship
from zara.utilities.database.validators import validate_slug
from zara.utilities.id57 import generate_lexicographical_uuid


class SoftDeleteMixin:
    deleted_at = DatabaseField(nullable=True, data_type=datetime.datetime)
    deleted_by = Relationship("User", has_one="deleted_by")

    async def delete(self):
        self.deleted_at = datetime.datetime.now()
        await super().delete()


class AuditMixin(SoftDeleteMixin):
    _audit = True
    created_at = DatabaseField(
        default_factory=datetime.datetime.now, data_type=datetime.datetime
    )
    updated_at = DatabaseField(
        default_factory=datetime.datetime.now, data_type=datetime.datetime
    )
    created_by = Relationship("User", has_one="created_by")
    updated_by = Relationship("User", has_one="updated_by")

    async def save(self):
        self.updated_at = datetime.datetime.now()
        await super().save()


class IdMixin:
    id = DatabaseField(
        primary_key=True,
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
    )


class MigratesOnCreation:
    async def post_init(self):
        from migrate import Migrator

        migrator = Migrator()
        pending = await migrator.compile_list_of_pending_migrations(
            [], only_schema=self.schema_name
        )
        for schema, migrations in pending.items():
            await migrator.run_migrations(target_schema=schema, pending=migrations)

        return True


class SettingsMixin(AuditMixin):
    """Some basic settings to get started."""

    user = Relationship("User", has_one="settings")
    display_mode = DatabaseField(default="system")  # light, dark, system, hi contrast
    language = DatabaseField(default="en", nullable=False)
    theme = DatabaseField(default="a theme, like blue or red")
    timezone = DatabaseField(default="a timezone.")
    reduced_motion = DatabaseField(default="system")
    receive_email_notifications = DatabaseField(default=False)
    receive_text_notifications = DatabaseField(default=False)
    has_opted_out_of_marketing = DatabaseField(default=False)


class SessionMixin(IdMixin):
    user = Relationship("User", has_many="sessions")
    access_token = DatabaseField(nullable=False)
    refresh_token = DatabaseField(nullable=False)
    expires_at = DatabaseField(nullable=True)
    last_active = DatabaseField(nullable=True)
    ip_address = DatabaseField(nullable=True)
    revoked_at = DatabaseField(nullable=True)
    user_agent = DatabaseField(nullable=True)
    created_at = DatabaseField(
        default_factory=datetime.datetime.now, data_type=datetime.datetime
    )


class RoleMixin(AuditMixin):
    """Role-based access control that has a defined subset of permissions."""

    name = DatabaseField(nullable=False)
    slug = DatabaseField(nullable=False, validate=validate_slug)
    is_custom = DatabaseField(nullable=False, data_type=bool, default=False)
    description = DatabaseField(nullable=False, data_type=str)
    role_permissions = Relationship("RolePermission", has_many="role")


class PermissionMixin(AuditMixin):
    """Permissions that form part of role-based access."""

    name = DatabaseField(nullable=False)
    slug = DatabaseField(nullable=False, validate=validate_slug)
    is_custom = DatabaseField(nullable=False, data_type=bool, default=False)
    description = DatabaseField(nullable=False, data_type=str)
    role_permissions = Relationship("RolePermission", has_many="permission")


class RolePermissionMixin(AuditMixin):
    """Map table for linking roles and permissions."""

    role = Relationship("Role", has_one="role_permission")
    permission = Relationship("Permission", has_one="role_permission")
