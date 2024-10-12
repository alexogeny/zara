import hashlib
import importlib
import inspect
import os
from typing import Dict, List, Type

import migration_generator
from zara.utilities.context import Context
from zara.utilities.database.orm import Model


class Migrator:
    def __init__(
        self,
        migrations_dir: str = "example/migrations",
        models_dir: str = "example/models",
        logger=None,
    ):
        self.migrations_dir = migrations_dir
        self.models_dir = models_dir
        self.models: Dict[str, Type[Model]] = {}
        self.migration_generator = None
        self.logger = logger

    def get_migration_files(self) -> List[str]:
        return sorted(
            [f for f in os.listdir(self.migrations_dir) if f.endswith(".migration.py")]
        )

    def get_migration_hash(self, filename: str) -> str:
        """Generate a hash for a migration file."""
        filepath = os.path.join(self.migrations_dir, filename)
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def collect_models(self):
        for root, _, files in os.walk(self.models_dir):
            for file in files:
                if file.endswith("_model.py"):
                    module_path = os.path.join(root, file)
                    module_name = os.path.splitext(file)[0]

                    # Use exec() to load and execute the module
                    with open(module_path, "r") as file:
                        code = file.read()
                        module_globals = {}
                        exec(code, module_globals)

                    # Gather the models from the module that subclasses Model
                    for name, obj in module_globals.items():
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, Model)
                            and obj is not Model
                        ):
                            self.models[name] = obj

        self.migration_generator = migration_generator.MigrationGenerator(
            self.migrations_dir, self.models
        )

    def generate_migration(self, name: str, schemas: list[str]):
        """Generate a migration file for the given name and schemas."""
        return self.migration_generator.generate_migration(name, schemas)

    def get_newest_migration(self):
        migrations = sorted(
            [f for f in os.listdir(self.migrations_dir) if f.endswith(".migration.py")]
        )
        return migrations[-1] if migrations else None

    async def is_schema_on_latest_version(self, schema):
        latest_migration = self.get_newest_migration()
        if not latest_migration:
            return True
        migration_hash = self.get_migration_hash(latest_migration)
        db = Context.get_db()

        if not await db.schema_exists(schema):
            await db.create_schema(schema)
        elif not await db.table_exists("migrations", schema=schema):
            await db.execute_in_schema(
                "CREATE TABLE migrations (migration_hash VARCHAR(255) PRIMARY KEY, name VARCHAR(255), applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
                schema=schema,
            )

        result = await db.execute_in_schema(
            "SELECT * FROM migrations WHERE migration_hash = $1",
            migration_hash,
            schema=schema,
            fetch_mode=True,
        )
        if result:
            return True
        return False

    async def compile_list_of_pending_migrations(self, schemas, only_schema=None):
        """Compile a list of pending migrations for each schema or the specific schema."""
        db = Context.get_db()

        migration_files = sorted(
            [f for f in os.listdir(self.migrations_dir) if f.endswith(".migration.py")]
        )
        pending = {}
        for schema in schemas if not only_schema else [only_schema]:
            if await self.is_schema_on_latest_version(schema):
                continue
            applied_migrations = await db.execute_in_schema(
                "SELECT * FROM migrations", schema=schema, fetch_mode=True
            )
            for f in migration_files:
                if f not in [m["name"] for m in applied_migrations]:
                    if schema not in pending:
                        pending[schema] = []
                    pending[schema].append(migration_files[migration_files.index(f)])
        return pending

    async def list_schemas(self):
        db = Context.get_db()
        schemas = await db.execute_in_schema(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name != 'public'",
            fetch_mode=True,
        )

        schemas = ["public"] + [
            schema["schema_name"]
            for schema in schemas
            if not schema["schema_name"].startswith("pg_")
            and not schema["schema_name"] == "information_schema"
        ]

        return schemas

    async def run_migrations(self, target_schema=None, pending: List[str] = []):
        """Run the migrations for each schema or the specific schema."""
        conn = Context.get_db()
        schemas = await self.list_schemas()
        for migration in pending:
            migration_file = os.path.join(self.migrations_dir, migration)
            with open(migration_file, "r") as file:
                code = file.read()
                module_globals = {}
                exec(code, module_globals)

            schemas_to_run_on = (
                [target_schema]
                if target_schema
                else module_globals.get("SCHEMAS", schemas)
            )
            if not schemas_to_run_on:
                schemas_to_run_on = ["public"]
            for schema in schemas_to_run_on:
                await conn.set_schema(schema)
                if schema == "public":
                    await module_globals["public_upgrade"](conn)
                else:
                    await module_globals["upgrade"](conn)
                hash = self.get_migration_hash(migration)
                await conn.record_migration(hash, migration, schema)
                await conn.unset_schema()

    async def rollback_migrations(self, target_version, target_schema=None):
        """Rollback the migrations for each schema or the specific schema."""
        schemas = await self.list_schemas()
        if target_schema not in schemas and target_schema is not None:
            await self.create_schema(target_schema)
            schemas.append(target_schema)
        await self.compile_list_of_pending_migrations(
            schemas, target_version, only_schema=target_schema
        )
        for migration in reversed(self.migrations):
            migration_file = os.path.join(self.migrations_dir, migration["name"])
            spec = importlib.util.spec_from_file_location(
                migration["name"], migration_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            schemas_to_run_on = module.SCHEMAS if module.SCHEMAS else schemas
            for schema in schemas_to_run_on:
                await self.db.set_schema(schema)
                await module.downgrade()
                print(f"Rolled back migration: {migration['version']} to {schema}")
