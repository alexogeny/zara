"""ORM for asyncpg."""

import datetime
import os
from contextlib import asynccontextmanager
from copy import copy
from enum import Enum
from typing import Callable, Dict, Optional, Type

import asyncpg
import orjson

from zara.utilities.context import Context


class ModelRegistry:
    _models: Dict[str, Type["Model"]] = {}

    @classmethod
    def register(cls, model_class: Type["Model"]):
        cls._models[model_class.__name__] = model_class

    @classmethod
    def get(cls, model_name: str) -> Type["Model"]:
        return cls._models.get(model_name)


class AsyncDB:
    def __init__(self):
        self.connection_details = self.get_connection_details()
        self.pool: asyncpg.Pool | None = None

    def get_connection_details(self):
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://user:password@localhost/dbname",
        )
        auth_part, host_part = db_url.split("@")
        host_name, db_name = host_part.split("/")
        u, p = auth_part.split("//")[1].split(":")
        details = {
            "host": host_name.split(":")[0],
            "port": 5432,
            "user": u,
            "password": p,
            "database": db_name,
        }
        return details

    async def setup_pool(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(**self.connection_details)

    async def close_pool(self):
        if self.pool:
            await self.pool.close()

    @asynccontextmanager
    async def acquire(self):
        if self.pool is None:
            await self.setup_pool()
        async with self.pool.acquire() as conn:
            yield conn


class DatabaseManager:
    def __init__(self, db: AsyncDB, schema: str = "public", logger=None):
        self.db = db
        self.schema = schema
        self.logger = logger

    async def bootstrap(self):
        from migrate import Migrator

        migrator = Migrator(logger=self.logger)
        schema_list = await migrator.list_schemas()
        pending = await migrator.compile_list_of_pending_migrations(schema_list)
        for schema, migrations in pending.items():
            await migrator.run_migrations(schema, migrations)

    @asynccontextmanager
    async def transaction(self, schema="public"):
        async with self.db.acquire() as conn:
            async with conn.transaction():
                yield TransactionContext(
                    conn, schema=schema or self.schema, logger=self.logger
                )


class TransactionContext:
    def __init__(self, conn, schema="public", logger=None):
        self.conn = conn
        self.schema = schema
        self.overrode_schema = None
        self.logger = logger
        self.logger.debug(f"Spawning transaction context in schema {schema}")

    async def execute(
        self, statement, *values, fetch_mode=None, public=False, schema=None
    ):
        self.logger.debug(f"running {statement} on {self.schema} with values {values}")
        if not self.overrode_schema:
            if schema is not None:
                await self.set_schema(schema)
            elif self.schema and not public:
                await self.set_schema(self.schema)
            elif public:
                await self.set_schema("public")
        if fetch_mode:
            if values:
                result = await self.conn.fetch(statement, *values)
            else:
                result = await self.conn.fetch(statement)
        else:
            if values:
                result = await self.conn.execute(statement, *values)
            else:
                result = await self.conn.execute(statement)
        if self.schema and public and not self.overrode_schema:
            await self.set_schema(self.schema)
        return result

    async def execute_in_schema(
        self, statement, *values, schema="public", fetch_mode=None
    ):
        await self.set_schema(schema)
        return await self.execute(
            statement, *values, fetch_mode=fetch_mode, schema=schema
        )

    async def set_schema(self, schema):
        await self.conn.execute(f"SET search_path TO {schema}")
        self.overrode_schema = schema

    async def unset_schema(self):
        await self.conn.execute("SET search_path TO public")
        self.overrode_schema = None

    async def schema_exists(self, schema):
        result = await self.execute(
            f"SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = '{schema}')",
            fetch_mode=True,
        )
        return result[0]["exists"]

    async def create_schema(self, schema):
        await self.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        await self.execute_in_schema(
            f"CREATE TABLE IF NOT EXISTS {schema}.migrations (migration_hash VARCHAR(255) PRIMARY KEY, name VARCHAR(255), applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            schema=schema,
        )

    async def table_exists(self, table_name, schema="public"):
        await self.set_schema(schema)
        result = await self.execute(
            f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}')",
            fetch_mode=True,
            public=schema == "public",
        )
        return result[0]["exists"]

    async def table_has_data(self, table_name, schema="public"):
        await self.set_schema(schema)
        result = await self.execute(
            f"SELECT EXISTS (SELECT 1 FROM {table_name})", fetch_mode=True
        )
        return result[0]["exists"]

    async def record_migration(self, migration_hash, migration_name, schema="public"):
        await self.set_schema(schema)
        await self.execute(
            "INSERT INTO migrations (migration_hash, name, applied_at) VALUES ($1, $2, CURRENT_TIMESTAMP)",
            migration_hash,
            migration_name,
        )


class DatabaseField:
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
        validate: Optional[Callable] = None,
    ):
        self.default = default
        self.default_factory = default_factory
        self.primary_key = primary_key
        self.auto_increment = auto_increment
        self.nullable = nullable
        self.index = index
        self.unique = unique
        self.length = length
        self._data_type = data_type
        self.private = private
        self.name = None
        self.validate = validate

    def __set_name__(self, owner, name):
        self.name = name
        if self._data_type is None and "__annotations__" in owner.__dict__:
            self._data_type = owner.__annotations__get(name)

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

    def get_enum(self):
        if isinstance(self._data_type, type) and issubclass(self._data_type, Enum):
            return self._data_type
        return None

    @property
    def data_type(self):
        if self._data_type is str:
            return "VARCHAR"
        elif self._data_type is int:
            return "INTEGER"
        elif self._data_type is float:
            return "FLOAT"
        elif self._data_type is bool:
            return "BOOLEAN"
        elif self._data_type is datetime.datetime:
            return "TIMESTAMP"
        elif isinstance(self._data_type, type) and issubclass(self._data_type, Enum):
            return self._data_type.__name__
        return "TEXT"


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

    def resolve_foreign_table_name(self):
        related_model = ModelRegistry.get(self.related_model_name)
        return related_model._get_full_table_name()

    def _sql_column_name(self):
        if self.has_one:
            return f"{self.has_one}"
        return None

    def as_fkname(self, model_name: str):
        if self.has_one:
            return f"fk_{model_name}_{self.name}"
        return None

    @property
    def data_type(self):
        if self.has_one:
            return "VARCHAR"
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
        self._allow_private = True
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
        if isinstance(attr, DatabaseField) and attr.private and not self._allow_private:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )
        return attr

    def dict(self, include_private=False):
        _allow_private = copy(self._allow_private)
        self._allow_private = include_private
        try:
            result = {
                field.name: getattr(self, field.name)
                for field in self.__class__.__dict__.values()
                if isinstance(field, DatabaseField)
                and (not field.private or (include_private and field.private))
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
            self._allow_private = _allow_private
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
        db = Context.get_db()
        if kwargs:
            row = await db.execute(query, *kwargs.values(), fetch_mode=True)
        else:
            query = query.replace("WHERE ", "LIMIT 1")
            row = await db.execute(query, fetch_mode=True)
        if row:
            instance = cls(**dict(row[0]))
            instance._loaded_fields = set(row[0].keys())
            instance._changed_fields.clear()
            if include:
                await instance.load_relationships(include)
            return instance
        return None

    @classmethod
    async def first_or_create(cls, **kwargs):
        result = await cls.get(**kwargs)
        if isinstance(result, Model):
            return result
        return await cls.create(cls())

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

        db = Context.get_db()
        rows = await db.execute(
            query,
            *[v for k, v in kwargs.items() if k not in ["order_by", "limit"]],
            fetch_mode=True,
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

    async def create(self, **kwargs):
        # instance = cls(**kwargs)
        await self.save()
        return self

    async def save(self):
        fields = [
            field
            for field in self._get_mro_fields().values()
            if isinstance(field, DatabaseField)
        ]
        existing_entity = "id" in self._loaded_fields or self._changed_fields
        if existing_entity:
            if not self._changed_fields:
                return  # No changes to save

            query = f"UPDATE {self._get_full_table_name()} SET "
            updates = [
                f"{field} = ${i+1}"
                for i, field in enumerate(
                    [f for f in self._changed_fields if f != "id"]
                )
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
            query = f"INSERT INTO {self._get_full_table_name()} ("
            query += ", ".join(field.name for field in fields)
            query += ") VALUES ("
            query += ", ".join(f"${i+1}" for i in range(len(fields)))
            query += ") RETURNING id"
            values = [getattr(self, field.name) for field in fields]
        db = Context.get_db()
        result = await db.execute(
            query, *values, fetch_mode=True, public=self.is_public
        )
        if result:
            self.id = result[0]["id"]

        self._changed_fields.clear()

        if not existing_entity:
            if "post_init" in self.__class__.__dict__:
                callable = self.__class__.__dict__["post_init"]
                await callable(self)
        elif "post_save" in self.__class__.__dict__:
            callable = self.__class__.__dict__["post_save"]
            await callable(self)

        return self

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

    def _get_table_sql(self):
        return (
            f"CREATE TABLE {self._get_full_table_name()} (\n    "
            + ",\n    ".join(self._get_fields_for_table_spec())
            + "\n)"
        )

    def _get_class_fields(self):
        return self.__class__.__dict__

    def _get_mro_fields(self):
        fields = {}
        for base in self.__class__.mro():
            if base is not object:
                for name, field in base.__dict__.items():
                    if isinstance(field, DatabaseField) or isinstance(
                        field, Relationship
                    ):
                        fields[name] = field
        return fields

    @property
    def is_public(self):
        for base in self.__class__.mro():
            if base.__name__ != "Public":
                continue
            if "_schema" not in base.__dict__:
                continue
            if base.__dict__["_schema"] == "public":
                return True
        return False

    def _get_fields_for_table_spec(self):
        fields = []
        for base in self.__class__.mro():
            if base is not object:
                for name, field in base.__dict__.items():
                    if isinstance(field, DatabaseField):
                        fields.append(
                            f"{name} {self._get_field_type(field)}{self._get_field_params(field)}"
                        )
                    elif isinstance(field, Relationship):
                        if field.has_one:
                            column_name = field._sql_column_name()
                            fields.append(
                                f"{column_name} {self._get_field_type(field)}{self._get_field_length(field)}{self._get_field_params(field)}"
                            )
        return fields

    def _get_field_params(self, field: DatabaseField | Relationship):
        if isinstance(field, Relationship):
            return ""
        params = []
        if field.primary_key:
            params.append("PRIMARY KEY")
        if field.auto_increment:
            params.append("AUTOINCREMENT")
        if not field.nullable:
            params.append("NOT NULL")
        if field.unique:
            params.append("UNIQUE")
        return " " + " ".join(params)

    def _get_field_length(self, field: DatabaseField | Relationship):
        if isinstance(field, Relationship):
            return "(30)"
        if field.length and field.data_type is str:
            return f"({field.length})"
        return ""

    def _get_field_type(self, field: DatabaseField | Relationship):
        if isinstance(field, Relationship):
            return "VARCHAR"
        if field.data_type is str:
            return f"VARCHAR({field.length or 255})"
        elif field.data_type is int:
            return "INTEGER"
        elif field.data_type is float:
            return "FLOAT"
        elif field.data_type is bool:
            return "BOOLEAN"
        elif field.data_type is datetime.datetime:
            return "TIMESTAMP"
        else:
            return "TEXT"

    def _get_relation_constraints(self):
        constraints = []
        for name, field in self._get_mro_fields().items():
            if isinstance(field, Relationship):
                if field.has_one:
                    column_name = field._sql_column_name()
                    constraints.append(
                        f"ALTER TABLE {self._get_full_table_name()} ADD CONSTRAINT fk_{self._table_name}_{name} FOREIGN KEY ({column_name}) REFERENCES {field.resolve_foreign_table_name()}(id)"
                    )
        return constraints

    def _get_indexes(self):
        indexes = []
        for name, field in self._get_mro_fields().items():
            if isinstance(field, DatabaseField):
                if field.index:
                    indexes.append(
                        f"CREATE INDEX idx_{self._table_name}_{name} ON {self._get_full_table_name()} ({name})"
                    )
        return indexes


class Public:
    """Mixin to set the schema to public."""

    _schema = "public"
