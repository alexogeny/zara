import hashlib
import importlib
import inspect
import json
import os
from datetime import datetime

import asyncpg

from zara.utilities.database.orm import DatabaseField, Model


class Migration:
    def __init__(self, version, name, schemas, changes):
        self.version = version
        self.name = name
        self.schemas = schemas
        self.changes = changes

    async def upgrade(self, conn):
        for schema in self.schemas:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {schema}.migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255),
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        for change in self.changes:
            await change.apply(conn)

    async def downgrade(self, conn):
        for change in reversed(self.changes):
            await change.revert(conn)


class ModelChange:
    async def apply(self, conn):
        raise NotImplementedError

    async def revert(self, conn):
        raise NotImplementedError


class AddField(ModelChange):
    def __init__(self, model, field_name, field):
        self.model = model
        self.field_name = field_name
        self.field = field

    async def apply(self, conn):
        table_name = f"{self.model._schema}.{self.model._table_name}"
        query = f"ALTER TABLE {table_name} ADD COLUMN {self.field_name} {self.get_sql_type()}"
        await conn.execute(query)

    async def revert(self, conn):
        table_name = f"{self.model._schema}.{self.model._table_name}"
        query = f"ALTER TABLE {table_name} DROP COLUMN {self.field_name}"
        await conn.execute(query)

    def get_sql_type(self):
        # Map Python types to SQL types
        type_map = {
            int: "INTEGER",
            str: "TEXT",
            float: "REAL",
            bool: "BOOLEAN",
            datetime: "TIMESTAMP",
        }
        return type_map.get(self.field.data_type, "TEXT")


class RemoveField(ModelChange):
    def __init__(self, model, field_name):
        self.model = model
        self.field_name = field_name

    async def apply(self, conn):
        table_name = f"{self.model._schema}.{self.model._table_name}"
        query = f"ALTER TABLE {table_name} DROP COLUMN {self.field_name}"
        await conn.execute(query)

    async def revert(self, conn):
        # Reverting a removed field is tricky as we don't have the original field definition
        # For simplicity, we'll add it back as TEXT, but in a real-world scenario,
        # you might want to store more information about the original field
        table_name = f"{self.model._schema}.{self.model._table_name}"
        query = f"ALTER TABLE {table_name} ADD COLUMN {self.field_name} TEXT"
        await conn.execute(query)


class MigrationManager:
    def __init__(self, migrations_dir, db_url, models_state_file, model_modules=None):
        self.migrations_dir = migrations_dir
        self.db_url = db_url
        self.migrations = []
        self.models_state_file = models_state_file
        self.model_modules = model_modules or []

    async def load_migrations(self):
        self.migrations = []
        for filename in sorted(os.listdir(self.migrations_dir)):
            if filename.endswith(".migration.py"):
                module_name = filename[:-3]
                module = importlib.import_module(f"migrations.{module_name}")
                migration = module.Migration()
                self.migrations.append(migration)

    def find_model_classes(self):
        models = []

        # Find models in specified modules
        for module_name in self.model_modules:
            module = importlib.import_module(module_name)
            models.extend(self._find_models_in_module(module))

        # Find models in .model.py files in current working directory
        for root, dirs, files in os.walk(os.getcwd()):
            for file in files:
                if file.endswith(".model.py"):
                    module_name = os.path.splitext(file)[0]  # Remove .py extension
                    try:
                        spec = importlib.util.spec_from_file_location(
                            module_name, os.path.join(root, file)
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        models.extend(self._find_models_in_module(module))
                    except Exception as e:
                        print(f"Error loading model file {file}: {e}")

        return models

    def _find_models_in_module(self, module):
        return [
            obj
            for name, obj in inspect.getmembers(module)
            if inspect.isclass(obj) and issubclass(obj, Model) and obj != Model
        ]

    async def apply_migrations(self, target_version=None):
        async with asyncpg.create_pool(self.db_url) as pool:
            async with pool.acquire() as conn:
                for migration in self.migrations:
                    if target_version and migration.version > target_version:
                        break
                    # Check if migration has been applied
                    for schema in migration.schemas:
                        result = await conn.fetchrow(
                            f"SELECT * FROM {schema}.migrations WHERE version = $1",
                            migration.version,
                        )
                        if not result:
                            await migration.upgrade(conn)
                            await conn.execute(
                                f"INSERT INTO {schema}.migrations (version, name) VALUES ($1, $2)",
                                migration.version,
                                migration.name,
                            )
                    print(f"Applied migration: {migration.version} {migration.name}")

    async def rollback_migrations(self, target_version):
        async with asyncpg.create_pool(self.db_url) as pool:
            async with pool.acquire() as conn:
                for migration in reversed(self.migrations):
                    if migration.version <= target_version:
                        break
                    await migration.downgrade(conn)
                    for schema in migration.schemas:
                        await conn.execute(
                            f"DELETE FROM {schema}.migrations WHERE version = $1",
                            migration.version,
                        )
                    print(
                        f"Rolled back migration: {migration.version} {migration.name}"
                    )

    def generate_migration(self, models, previous_hash):
        current_hash = self._hash_models(models)
        if current_hash == previous_hash:
            print("No changes detected.")
            return previous_hash

        version = datetime.now().strftime("%Y%m%d%H%M%S")
        name = f"migration_{version}"
        schemas = self._detect_schemas(models)
        changes = self._detect_changes(models, previous_hash)

        migration_content = self._generate_migration_content(
            version, name, schemas, changes
        )

        filename = f"{version}_{name}.migration.py"
        with open(os.path.join(self.migrations_dir, filename), "w") as f:
            f.write(migration_content)

        # Save the current state of models
        self._save_models_state(current_hash, models)

        print(f"Generated migration: {filename}")
        return current_hash

    def _hash_models(self, models):
        model_definitions = []
        for model in models:
            fields = {
                name: self._serialize_field(field)
                for name, field in model.__dict__.items()
                if isinstance(field, DatabaseField)
            }
            model_definitions.append((model.__name__, fields))
        return hashlib.md5(
            json.dumps(model_definitions, sort_keys=True).encode()
        ).hexdigest()

    def _serialize_field(self, field):
        return {
            "type": field.__class__.__name__,
            "args": {k: v for k, v in field.__dict__.items() if not k.startswith("_")},
        }

    def _save_models_state(self, hash_value, models):
        state = {
            "hash": hash_value,
            "models": {
                model.__name__: {
                    name: self._serialize_field(field)
                    for name, field in model.__dict__.items()
                    if isinstance(field, DatabaseField)
                }
                for model in models
            },
        }

        with open(self.models_state_file, "r+") as f:
            try:
                states = json.load(f)
            except json.JSONDecodeError:
                states = []

            states.append(state)

            f.seek(0)
            json.dump(states, f, indent=2)
            f.truncate()

    def _load_previous_models(self, previous_hash):
        with open(self.models_state_file, "r") as f:
            states = json.load(f)

        previous_state = next(
            (s for s in reversed(states) if s["hash"] == previous_hash), None
        )

        if not previous_state:
            return []

        return [
            type(
                name,
                (Model,),
                {
                    name: self._deserialize_field(name, field_data)
                    for name, field_data in fields.items()
                },
            )
            for name, fields in previous_state["models"].items()
        ]

    def _deserialize_field(self, name, field_data):
        field_class = getattr(
            importlib.import_module("zara.utilities.database.orm"), field_data["type"]
        )
        return field_class(**field_data["args"])

    def _detect_schemas(self, models):
        return list(set(model._schema for model in models if hasattr(model, "_schema")))

    def _detect_changes(self, current_models, previous_hash):
        # Load previous models (you need to implement a way to store and retrieve previous model states)
        previous_models = self._load_previous_models(previous_hash)

        changes = []
        for model in current_models:
            prev_model = next(
                (m for m in previous_models if m.__name__ == model.__name__), None
            )
            if prev_model:
                # Detect field changes
                current_fields = {
                    name: field
                    for name, field in model.__dict__.items()
                    if isinstance(field, DatabaseField)
                }
                prev_fields = {
                    name: field
                    for name, field in prev_model.__dict__.items()
                    if isinstance(field, DatabaseField)
                }

                for name, field in current_fields.items():
                    if name not in prev_fields:
                        changes.append(AddField(model, name, field))

                for name in prev_fields:
                    if name not in current_fields:
                        changes.append(RemoveField(model, name))
            else:
                # New model, add all fields
                for name, field in model.__dict__.items():
                    if isinstance(field, DatabaseField):
                        changes.append(AddField(model, name, field))

        return changes

    def _generate_migration_content(self, version, name, schemas, changes):
        content = f"""from zara.utilities.database.orm import Migration, AddField, RemoveField

class {name.capitalize()}(Migration):
    def __init__(self):
        changes = [
            {', '.join(str(change) for change in changes)}
        ]
        super().__init__('{version}', '{name}', {schemas}, changes)
"""
        return content


# Usage remains similar, but now includes database connection
migration_manager = MigrationManager(
    "migrations", "postgresql://user:password@localhost/dbname"
)
models = migration_manager.find_model_classes()
previous_hash = "previous_hash_here"  # You need to store and retrieve this
new_hash = migration_manager.generate_migration(models, previous_hash)
