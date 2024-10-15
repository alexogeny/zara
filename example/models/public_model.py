from datetime import datetime, timedelta
from enum import Enum

import orjson

from example.models.mixins import IdMixin, MigratesOnCreation
from zara.utilities.database.orm import DatabaseField, Model, Public, Relationship
from zara.utilities.database.validators import validate_slug
from zara.utilities.id57 import generate_lexicographical_uuid


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


class Customer(Model, Public, MigratesOnCreation):
    _table_name = "customers"
    id = DatabaseField(
        primary_key=True,
        data_type=str,
        length=30,
        default_factory=generate_lexicographical_uuid,
    )
    name = DatabaseField(data_type=str, unique=True, index=True)

    @property
    def schema_name(self):
        return self.name.lower().strip().replace("-", "_").replace(" ", "_")


def dumb_datetime():
    return datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)


class Configuration(Model, Public):
    _table_name = "configuration"
    token_secret = DatabaseField(
        nullable=False,
        default_factory=generate_lexicographical_uuid,
        data_type=str,
        length=30,
        private=True,
    )


class Features(Model, Public, IdMixin):
    _table_name = "features"
    name: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=128,
    )
    slug: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=128,
        validate=validate_slug,
    )
    description: str = DatabaseField(
        nullable=False,
        data_type=str,
        length=255,
    )


class UsageLimit(Model, Public, IdMixin):
    _table_name = "usage_limits"
    license = Relationship("License", has_one="license")
    features = Relationship("Features", has_one="features")
    customer = Relationship("Customer", has_one="customer")
    limit_type = DatabaseField(
        nullable=False,
        data_type=LimitType,
        default=LimitType.UNLIMITED,
        length=max([len(LimitType.value) for LimitType in LimitType]),
    )
    max_value = DatabaseField(
        nullable=False,
        data_type=int,
    )
    current_value = DatabaseField(
        nullable=False,
        data_type=int,
        default=0,
    )
    reset_period = DatabaseField(
        nullable=True,
        data_type=ResetPeriod,
        length=max([len(ResetPeriod.value) for ResetPeriod in ResetPeriod]),
    )
    last_reset = DatabaseField(
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


class License(Model, Public, IdMixin):
    _table_name = "license"
    customer = Relationship("Customer", has_one="license")
    usage_limits = Relationship("UsageLimit", has_many="license")
    license_tier = DatabaseField(
        nullable=False,
        data_type=LicenseTier,
        default=LicenseTier.FREE_TRIAL,
        length=max([len(LicenseTier.value) for LicenseTier in LicenseTier]),
    )
    feature_template_id = DatabaseField(
        nullable=False,
        data_type=str,
        length=30,
    )
    custom_features = DatabaseField(
        nullable=True,
        data_type=str,
        length=1000,
    )
    max_users = DatabaseField(
        nullable=False,
        data_type=int,
        default=1,
    )
    price = DatabaseField(
        nullable=False,
        data_type=float,
        default=0.0,
    )
    billing_cycle = DatabaseField(
        nullable=False,
        data_type=BillingCycle,
        default=BillingCycle.MONTHLY,
        length=max([len(BillingCycle.value) for BillingCycle in BillingCycle]),
    )
    start_date = DatabaseField(
        nullable=False,
        data_type=datetime,
        default=lambda: dumb_datetime(),
    )
    expiration_date = DatabaseField(
        nullable=True,
        data_type=datetime,
    )
    is_active: bool = DatabaseField(
        nullable=False,
        data_type=bool,
        default=True,
    )
    stripe_customer_id = DatabaseField(
        nullable=True,
        data_type=str,
        length=255,
    )
    stripe_subscription_id = DatabaseField(
        nullable=True,
        data_type=str,
        length=255,
    )
    free_trial_expires_at = DatabaseField(
        nullable=True,
        data_type=datetime,
    )
    free_trial_started_at = DatabaseField(
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
