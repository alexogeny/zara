"""ORM for asyncpg."""

import asyncio
import datetime
import threading
from contextvars import ContextVar
from typing import Dict, Type

import asyncpg
import orjson
import uvloop


class ModelRegistry:
    _models: Dict[str, Type["Model"]] = {}

    @classmethod
    def register(cls, model_class: Type["Model"]):
        cls._models[model_class.__name__] = model_class

    @classmethod
    def get(cls, model_name: str) -> Type["Model"]:
        return cls._models.get(model_name)


class AsyncDB:
    """AsyncDB is a context manager that can be used to run queries asynchronously."""

    def __init__(self, connection_details: dict):
        self.connection_details = connection_details
        self.db = None
        self.loop = uvloop.new_event_loop()
        self.thread = threading.Thread(target=self._runner)
        self.context = ContextVar("context")
        self.context.db = None

        # Start the thread
        self.thread.start()

    def _runner(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._setup_db())

    async def _setup_db(self):
        self.db = await asyncpg.create_pool(**self.connection_details)

    async def __aenter__(self):
        """Enter the context manager."""
        await self.db.acquire()
        self.context.db = self.db
        return self.context

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager."""
        self.context.db.release()
        self.context.db = None

    def __getattr__(self, name):
        """Get the attribute from the context."""
        return getattr(self.context.db, name)

    def __del__(self):
        """Delete the context manager."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()


class DatabaseField:
    """Defines a field that exists in the database."""

    def __init__(
        self,
        default=None,
        default_factory=None,
        primary_key=False,
        auto_increment=False,
        nullable=True,
        index=False,
        unique=False,
        length=None,
        data_type=str,
        private=False,
    ):
        self.default = default
        self.default_factory = default_factory
        self.primary_key = primary_key
        self.auto_increment = auto_increment
        self.nullable = nullable
        self.index = index
        self.unique = unique
        self.length = length
        self.data_type = data_type
        self.private = private
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name
        if self.data_type is None and "__annotations__" in owner.__dict__:
            self.data_type = owner.__annotations__get(name)

    def __repr__(self):
        return f"<DatabaseField: {self.name}>"

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.private and not getattr(instance, "_allow_private", False):
            raise AttributeError(f"Private field {self.name} not allowed")
        return instance.__dict__.get(self.name, self.get_default())

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value

    def get_default(self):
        if callable(self.default_factory):
            return self.default_factory()
        return self.default


class Relationship:
    def __init__(
        self,
        model,
        has_one=None,
        has_many=None,
        owns_one=None,
        limit=None,
        order_by=None,
    ):
        self.related_model_name = model
        self.name = None
        self.has_one = has_one
        self.has_many = has_many
        self.owns_one = owns_one
        self.limit = limit
        self.order_by = order_by

    def __repr__(self):
        return f"<Relationship: {self.related_model_name}>"

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.name not in instance.__dict__:
            return None
        return instance.__dict__[self.name]

    async def load(self, instance):
        related_model = ModelRegistry.get(self.related_model_name)
        if self.has_one:
            foreign_key = getattr(instance, f"{self.has_one}_id", None)
            if foreign_key:
                return await related_model.get(id=foreign_key)
        elif self.has_many:
            foreign_key = getattr(instance, "id", None)
            if foreign_key:
                query = {f"{self.has_many}_id": foreign_key}
                if self.order_by:
                    query["order_by"] = self.order_by
                if self.limit:
                    query["limit"] = self.limit
                return await related_model.filter(**query)
        elif self.owns_one:
            foreign_key = getattr(instance, "id", None)
            if foreign_key:
                return await related_model.get(**{f"{self.owns_one}_id": foreign_key})
        return None


class Model:
    """Base class for all models."""

    _table_name = None
    _schema = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ModelRegistry.register(cls)

    def __init__(self, **kwargs):
        self._changed_fields = set()
        self._loaded_fields = set()
        self._loaded_relationships = set()
        self._allow_private = False
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._changed_fields.clear()

    def __setattr__(self, key, value):
        if key not in (
            "_changed_fields",
            "_loaded_fields",
            "_loaded_relationships",
        ) and hasattr(self, "_changed_fields"):
            self._changed_fields.add(key)
        super().__setattr__(key, value)

    def __getattr__(self, name):
        if name.startswith("_") or name == "dict" or name == "json":
            return super().__getattr__(name)
        attr = super().__getattribute__(name)
        if isinstance(attr, DatabaseField) and attr.private:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )
        return attr

    def dict(self, include_private=False):
        self._allow_private = include_private
        try:
            result = {
                field.name: getattr(self, field.name)
                for field in self.__class__.__dict__.values()
                if isinstance(field, DatabaseField)
                and (not field.private or include_private)
            }
            for rel_name in self._loaded_relationships:
                rel_value = getattr(self, rel_name)
                if isinstance(rel_value, list):
                    result[rel_name] = [
                        rel.dict(include_private=include_private) for rel in rel_value
                    ]
                elif isinstance(rel_value, Model):
                    result[rel_name] = rel_value.dict(include_private=include_private)
                else:
                    result[rel_name] = rel_value
        finally:
            self._allow_private = False
        return result

    def json(self, include_private=False):
        return orjson.dumps(self.dict(include_private=include_private))

    @classmethod
    async def get(cls, fields=None, include=None, **kwargs):
        if fields is None:
            fields = "*"
        else:
            fields = ", ".join(fields)

        query = f"SELECT {fields} FROM {cls._get_full_table_name()} WHERE "
        conditions = [f"{key} = ${i+1}" for i, key in enumerate(kwargs.keys())]
        query += " AND ".join(conditions)

        async with AsyncDB.context.db.acquire() as conn:
            row = await conn.fetchrow(query, *kwargs.values())
            if row:
                instance = cls(**dict(row))
                instance._loaded_fields = set(row.keys())
                instance._changed_fields.clear()
                if include:
                    await instance.load_relationships(include)
                return instance
        return None

    @classmethod
    async def filter(
        cls, fields=None, include=None, order_by=None, limit=None, **kwargs
    ):
        if fields is None:
            fields = "*"
        else:
            fields = ", ".join(fields)

        query = f"SELECT {fields} FROM {cls._get_full_table_name()} WHERE "
        conditions = [
            f"{key} = ${i+1}"
            for i, key in enumerate(kwargs.keys())
            if key not in ["order_by", "limit"]
        ]
        query += " AND ".join(conditions)

        if order_by:
            query += f" ORDER BY {order_by}"
        if limit:
            query += f" LIMIT {limit}"

        async with AsyncDB.context.db.acquire() as conn:
            rows = await conn.fetch(
                query, *[v for k, v in kwargs.items() if k not in ["order_by", "limit"]]
            )
            instances = [cls(**dict(row)) for row in rows]
            for instance in instances:
                instance._loaded_fields = set(dict(rows[0]).keys())
                instance._changed_fields.clear()
                if include:
                    await instance.load_relationships(include)
            return instances

    async def load_relationships(self, include):
        for relationship_name in include:
            if hasattr(self, relationship_name) and isinstance(
                getattr(self.__class__, relationship_name), Relationship
            ):
                relationship = getattr(self.__class__, relationship_name)
                setattr(self, relationship_name, await relationship.load(self))
                self._loaded_relationships.add(relationship_name)

    @classmethod
    async def create(cls, **kwargs):
        instance = cls(**kwargs)
        await instance.save()
        return instance

    async def save(self):
        fields = [
            field
            for field in self.__class__.__dict__.values()
            if isinstance(field, DatabaseField)
        ]

        if hasattr(self, "id") and self.id:
            # Update existing record
            if not self._changed_fields:
                return  # No changes to save

            query = f"UPDATE {self._get_full_table_name()} SET "
            updates = [
                f"{field.name} = ${i+1}"
                for i, field in enumerate(fields)
                if field.name in self._changed_fields and field.name != "id"
            ]
            query += ", ".join(updates)
            query += f" WHERE id = ${len(updates) + 1}"
            values = [
                getattr(self, field.name)
                for field in fields
                if field.name in self._changed_fields and field.name != "id"
            ]
            values.append(self.id)
        else:
            # Insert new record
            query = f"INSERT INTO {self._get_full_table_name()} ("
            query += ", ".join(field.name for field in fields)
            query += ") VALUES ("
            query += ", ".join(f"${i+1}" for i in range(len(fields)))
            query += ") RETURNING id"
            values = [getattr(self, field.name) for field in fields]

        async with AsyncDB.context.db.acquire() as conn:
            result = await conn.fetchval(query, *values)
            if result and not hasattr(self, "id"):
                self.id = result

        self._changed_fields.clear()

    def __call__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        return self

    @classmethod
    def _get_full_table_name(cls):
        if cls._schema:
            return f"{cls._schema}.{cls._table_name}"
        return cls._table_name

    def is_relationship_loaded(self, relationship_name):
        return relationship_name in self._loaded_relationships

    async def refresh_relationship(self, relationship_name):
        if hasattr(self, relationship_name) and isinstance(
            getattr(self.__class__, relationship_name), Relationship
        ):
            relationship = getattr(self.__class__, relationship_name)
            setattr(self, relationship_name, await relationship.load(self))
            self._loaded_relationships.add(relationship_name)

    @classmethod
    def _get_model_class(cls, model_name):
        return globals()[model_name]

    def is_field_loaded(self, field_name):
        return field_name in self._loaded_fields

    def refresh_field(self, field_name):
        self._changed_fields.discard(field_name)


class Public:
    """Mixin to set the schema to public."""

    _schema = "public"


# Example usage:
class User(Public, Model):
    _table_name = "users"

    id = DatabaseField(primary_key=True, auto_increment=True)
    name = DatabaseField()
    age = DatabaseField(data_type=int)
    password_hash = DatabaseField(private=True)


# Mixin example
class TimestampMixin:
    created_at = DatabaseField(default_factory=datetime.now)
    updated_at = DatabaseField(default_factory=datetime.now)

    async def save(self):
        self.updated_at = datetime.now()
        await super().save()


class Post(TimestampMixin, Public, Model):
    _table_name = "posts"

    id = DatabaseField(primary_key=True, auto_increment=True)
    title = DatabaseField()
    content = DatabaseField()
    author = Relationship("User", has_one="posts")
