from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

import orjson

from zara.utilities.database.base import Model, Public
from zara.utilities.database.fields import (
    DatabaseField,
    HasMany,
    HasOne,
    Optional,
)
from zara.utilities.database.mixins import IdMixin, dumb_datetime
from zara.utilities.database.validators import validate_slug
from zara.utilities.id57 import generate_lexicographical_uuid

if TYPE_CHECKING:

    class Users:
        pass

    class Database:
        pass


class LicenseTier(Enum):
    FREE = "free"
    BASIC = "basic"
    MEDIUM = "medium"
    ENTERPRISE = "enterprise"
    FREE_TRIAL = "free_trial"


class LimitType(Enum):
    FIXED = "fixed"
    TIME = "time"
    PER_USER = "per_user"
    UNLIMITED = "unlimited"


class ResetPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BillingCycle(Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class UsageLimit(Model, Public, IdMixin):
    license_id: HasOne["License"] = HasOne["License"]
    feature_slug: HasOne["Feature"] = HasOne["Feature"]
    customer_id: HasOne["Customer"] = HasOne["Customer"]
    limit_type: LimitType = DatabaseField(
        nullable=False,
        data_type=LimitType,
        default=LimitType.UNLIMITED,
        length=max([len(LimitType.value) for LimitType in LimitType]),
    )
    max_value: int = DatabaseField(
        nullable=False,
        data_type=int,
    )
    current_value: int = DatabaseField(
        nullable=False,
        data_type=int,
        default=0,
    )
    reset_period: Optional[str] = DatabaseField(
        nullable=True,
        data_type=ResetPeriod,
        length=max([len(ResetPeriod.value) for ResetPeriod in ResetPeriod]),
    )
    last_reset: datetime = DatabaseField(
        nullable=False,
        data_type=datetime,
        default=lambda: dumb_datetime(),
    )

    async def check_and_update_limit(self, increment: int = 1) -> bool:
        if self.limit_type == LimitType.UNLIMITED:
            self.current_value += increment
            await self.save()
            return True
        if self.limit_type == LimitType.TEMPORAL:
            await self._reset_if_needed()

        if self.current_value + increment <= self.max_value:
            self.current_value += increment
            await self.save()
            return True
        return False

    async def _reset_if_needed(self):
        now = dumb_datetime()
        was_reset = False
        delta = now - self.last_reset
        if self.reset_period == ResetPeriod.DAILY and delta >= timedelta(days=1):
            self.current_value = 0
            self.last_reset = now
            was_reset = True
        elif self.reset_period == ResetPeriod.WEEKLY and delta >= timedelta(weeks=1):
            self.current_value = 0
            self.last_reset = now
            was_reset = True
        elif self.reset_period == ResetPeriod.MONTHLY and delta >= timedelta(days=30):
            self.current_value = 0
            self.last_reset = now
            was_reset = True
        if was_reset:
            await self.save()


class Configuration(Model, Public):
    token_secret: Optional[str] = DatabaseField(
        nullable=False,
        default=lambda: generate_lexicographical_uuid(),
        auto_increment=False,
        primary_key=False,
        data_type=str,
        length=30,
        private=True,
    )


class Customer(Model, Public, IdMixin):
    name: str = DatabaseField(nullable=False, data_type=str, length=255, unique=True)
    license_id: HasOne["License"] = HasOne["License"]


class Feature(Model, Public, IdMixin):
    name: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=255,
    )
    slug: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=255,
        validate=validate_slug,
    )
    description: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=1000,
    )


class FeatureTemplate(Model, Public, IdMixin):
    name: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=255,
    )
    slug: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=255,
        validate=validate_slug,
    )
    tier: LicenseTier = DatabaseField(
        nullable=False,
        data_type=LicenseTier,
    )
    features: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=1000,
    )

    def get_features(self):
        return orjson.loads(self.features)

    def set_features(self, feature_dict):
        self.features = orjson.dumps(feature_dict)


class License(Model, Public, IdMixin):
    customer_id: HasOne["Customer"] = HasOne["Customer"]
    usage_limits: HasMany["UsageLimit"] = HasMany["UsageLimit"]
    license_tier: LicenseTier = DatabaseField(
        nullable=False,
        data_type=LicenseTier,
        default=LicenseTier.FREE_TRIAL,
        length=max([len(LicenseTier.value) for LicenseTier in LicenseTier]),
    )
    feature_template_id: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=30,
    )
    custom_features: Optional[str] = DatabaseField(
        nullable=True,
        data_type=str,
        length=1000,
    )
    max_users: int = DatabaseField(
        nullable=False,
        data_type=int,
        default=1,
    )
    price: float = DatabaseField(
        nullable=False,
        data_type=float,
        default=0.0,
    )
    billing_cycle: str = DatabaseField(
        nullable=False,
        data_type=BillingCycle,
        default=BillingCycle.MONTHLY,
        length=max([len(BillingCycle.value) for BillingCycle in BillingCycle]),
    )
    start_date: datetime = DatabaseField(
        nullable=False,
        data_type=datetime,
        default=lambda: dumb_datetime(),
    )
    expiration_date: Optional[datetime] = DatabaseField(
        nullable=True,
        data_type=datetime,
    )
    is_active: bool = DatabaseField(
        nullable=False,
        data_type=bool,
        default=True,
    )
    stripe_customer_id: Optional[str] = DatabaseField(
        nullable=True,
        data_type=str,
        length=255,
    )
    stripe_subscription_id: Optional[str] = DatabaseField(
        nullable=True,
        data_type=str,
        length=255,
    )
    free_trial_expires_at: Optional[datetime] = DatabaseField(
        nullable=True,
        data_type=datetime,
    )
    free_trial_started_at: Optional[datetime] = DatabaseField(
        nullable=True,
        data_type=datetime,
    )

    def get_custom_features(self):
        return orjson.loads(self.custom_features) if self.custom_features else {}

    def set_custom_features(self, feature_dict):
        self.custom_features = orjson.dumps(feature_dict)

    @property
    def is_free_trial(self):
        return (
            self.license_tier == LicenseTier.FREE_TRIAL
            and self.free_trial_started_at is not None
            and dumb_datetime() < self.free_trial_expires_at
        )

    @property
    def free_trial_expired(self):
        return (
            self.license_tier == LicenseTier.FREE_TRIAL
            and self.free_trial_started_at is not None
            and dumb_datetime() > self.free_trial_expires_at
        )

    async def check_usage_limit(self, feature_slug: str, increment: int = 1) -> bool:
        for usage_limit in self.usage_limits:
            if usage_limit.feature_slug == feature_slug:
                return await usage_limit.check_and_update_limit(increment)
        return False
