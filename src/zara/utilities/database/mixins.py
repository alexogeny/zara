from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from .fields import Default, HasOne, Optional, Required

if TYPE_CHECKING:

    class User:
        def _get_table_name():
            return "user"


class MetaMixin:
    created_at: Required[datetime.datetime] = Default(
        datetime.datetime.now(tz=datetime.timezone.utc)
    )
    created_by: HasOne["User"] = HasOne["User"]
    updated_at: Optional[datetime.datetime] = None
    updated_by: HasOne["User"] = HasOne["User"]


class SoftDeleteMixin:
    deleted_at: Optional[datetime.datetime] = None
    deleted_by: HasOne["User"] = HasOne["User"]
