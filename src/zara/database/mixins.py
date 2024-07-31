from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from argon2 import PasswordHasher
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import (
    Mapped,
    as_declarative,
    declarative_base,
    declarative_mixin,
    declared_attr,
    mapped_column,
    relationship,
    sessionmaker,
)

password_hasher = PasswordHasher()
DATABASE_URL = "sqlite+aiosqlite:///./test.db"

Base = declarative_base()

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


@as_declarative()
class CreateTableName:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower().replace(" ", "_")


class PublicSchemaMixin:
    @declared_attr
    def __table_args__(cls):
        return {"schema": "public"}


class CustomerSchemaMixin:
    @declared_attr
    def __table_args__(cls):
        return {"schema": f"{cls.customer_name}"}


@declarative_mixin
class AuditMixin:
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    created_by: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=True)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=True)
    deleted_by: Mapped[UUID] = mapped_column(ForeignKey("user.id"), nullable=True)

    created_by_user: Mapped["User"] = relationship(
        back_populates="created_users", nullable=True
    )
    updated_by_user: Mapped["User"] = relationship(
        back_populates="updated_users", nullable=True
    )
    deleted_by_user: Mapped["User"] = relationship(
        back_populates="deleted_users", nullable=True
    )


@declarative_mixin
class PasswordMixin:
    @classmethod
    def hash_password(
        cls, password: str, app_salt: str, customer_salt: str, user_salt: str
    ) -> str:
        salted_password = f"{app_salt}{customer_salt}{user_salt}{password}"
        return password_hasher.hash(salted_password)

    @classmethod
    def verify_password(
        cls,
        hashed_password: str,
        password: str,
        app_salt: str,
        customer_salt: str,
        user_salt: str,
    ) -> bool:
        salted_password = f"{app_salt}{customer_salt}{user_salt}{password}"
        try:
            return password_hasher.verify(hashed_password, salted_password)
        except Exception:
            return False

    def set_password(
        self, password: str, app_salt: str, customer_salt: str, user_salt: str
    ) -> None:
        self.password = self.hash_password(password, app_salt, customer_salt, user_salt)


class BaseMixin(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    @classmethod
    async def create(cls, **kwargs: Any) -> Any:
        async with AsyncSessionLocal() as session:
            obj = cls(**kwargs)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    @classmethod
    async def get(cls, model_id: int) -> Optional[Any]:
        async with AsyncSessionLocal() as session:
            result = await session.get(cls, model_id)
            return result

    @classmethod
    async def update(cls, model_id: int, update_data: Dict[str, Any]) -> Optional[Any]:
        async with AsyncSessionLocal() as session:
            result = await session.get(cls, model_id)
            if result:
                for key, value in update_data.items():
                    setattr(result, key, value)
                await session.commit()
                await session.refresh(result)
            return result

    @classmethod
    async def delete(cls, model_id: int) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.get(cls, model_id)
            if result:
                await session.delete(result)
                await session.commit()

    @classmethod
    async def list(cls) -> List[Any]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(cls))
            return result.scalars().all()


class Customer(BaseMixin, PublicSchemaMixin):
    name = Column(String, unique=True, index=True)
    display_name = Column(String)
    customer_salt = Column(String)


class User(BaseMixin, CustomerSchemaMixin, AuditMixin, PasswordMixin):
    username = Column(String, unique=True, index=True)
    display_name = Column(String)
    password = Column(String)
    password_needs_update = Column(Boolean, default=False)
    user_salt = Column(String)
