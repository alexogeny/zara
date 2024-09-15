import datetime
import hashlib
import inspect
import os
import re
import sqlite3
from typing import List
from typing import Optional as TypingOptional

from .base import Model
from .fields import (
    AutoIncrement,
    DatabaseField,
    DatabaseFieldType,
    HasMany,
    HasOne,
    Optional,
    PrimaryKey,
    Required,
)
from .sqllex import AlterTable, DropTable, compare_sql_statements, parse_sql_statements


def translate_pgsql_to_sqlite(query):
    query = query.replace(
        "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
    ).replace("TIMESTAMP", "TEXT")
    # replace VARCHAR and VARCHAR(n) with TEXT
    query = re.sub(r"VARCHAR\(\d+\)", "TEXT", query)
    return query


class SchemaGenerator:
    def __init__(self):
        self.models = []

    def register_all_models(self, root_dir="."):
        """Look for all `*_model.py` files and register models from them."""
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith("_model.py"):  # Only process `*.model.py` files
                    model_path = os.path.join(root, file)
                    self._load_and_register_models(model_path)

    def _load_and_register_models(self, filepath):
        """Executes a model file and registers all models defined in it."""
        try:
            with open(filepath, "r") as file:
                # Prepare a local namespace for executing the file
                local_namespace = {}

                # Add imports and necessary context to the local namespace
                exec(
                    file.read(),
                    {
                        "datetime": datetime,
                        "Model": Model,
                        "AutoIncrement": AutoIncrement,
                        "HasMany": HasMany,
                        "Optional": Optional,
                        "PrimaryKey": PrimaryKey,
                        "Required": Required,
                        "TypingOptional": TypingOptional,
                        "HasOne": HasOne,
                        "DatabaseField": DatabaseField,
                        "DatabaseFieldType": DatabaseFieldType,
                    },
                    local_namespace,
                )

                # Inspect local namespace for classes that inherit from Model
                for name, obj in local_namespace.items():
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, Model)
                        and obj is not Model
                    ):
                        self.models.append(obj)
                        print(f"Registered model from {filepath}: {name}")
        except Exception as e:
            print(f"Failed to load models from {filepath}: {e}")

    def generate_create_table_sql(self, model_cls) -> str:
        """Generates the CREATE TABLE SQL for a given model."""
        table_name = model_cls._get_table_name()
        fields = model_cls._get_fields()

        sql = f"CREATE TABLE {table_name} (\n"
        field_lines = []
        index_lines = []
        compound_pk = None
        relation_lines = []
        for field_name, field_type in fields.items():
            print(field_name, field_type)
            print("===============")
            if isinstance(field_type, Required):
                field_lines.append(
                    f"    {field_name} {self._get_sql_type(field_type.field_type)} NOT NULL"
                )
            elif isinstance(field_type, Optional):
                field_lines.append(
                    f"    {field_name} {self._get_sql_type(field_type.field_type)}"
                )
            elif isinstance(field_type, HasOne):
                matching_model = next(
                    (m for m in self.models if m.__name__ == field_type.related_model),
                    None,
                )
                referenced_table = matching_model._get_table_name()
                foreign_key_constraint = (
                    f"ALTER TABLE {table_name} ADD CONSTRAINT fk_{table_name}_{field_name} "
                    f"FOREIGN KEY ({field_name}) REFERENCES {referenced_table}(id);\n"
                )
                relation_lines.append(foreign_key_constraint)
                field_lines.append(f"    {field_name} VARCHAR(30)")
            elif isinstance(field_type, DatabaseField):
                nullable = " NOT NULL" if field_type.nullable is False else ""
                if field_type.index is True:
                    index_lines.append(
                        self._generate_index_sql(
                            table_name, field_type.unique is True, [field_name]
                        )
                    )
                if (
                    field_type.primary_key is True
                    and field_type.auto_increment is False
                ):
                    if field_type.length is not None:
                        field_lines.append(
                            f"    {field_name} VARCHAR({field_type.length}) PRIMARY KEY"
                        )
                    else:
                        field_lines.append(f"    {field_name} INTEGER PRIMARY KEY")
                elif (
                    field_type.primary_key is True and field_type.auto_increment is True
                ):
                    field_lines.append(f"    {field_name} SERIAL PRIMARY KEY")
                elif field_type.auto_increment is True:
                    field_lines.append(f"    {field_name} SERIAL")
                else:
                    field_lines.append(
                        f"    {field_name} {self._get_sql_type(field_type.data_type)}{nullable}"
                    )

        if compound_pk:
            field_lines.append(f"    PRIMARY KEY ({', '.join(compound_pk)})")
        sql += ",\n".join(field_lines)
        sql += "\n);\n"
        return sql, relation_lines, index_lines

    def _generate_index_sql(self, table_name: str, unique, fields):
        unique = "UNIQUE " if unique else ""
        fields = ", ".join(fields)
        return f"CREATE {unique}INDEX idx_{table_name}_{fields.replace(' ', '_')} ON {table_name} ({fields});"

    def _get_sql_type(self, python_type):
        """Maps Python types to SQL types."""
        if python_type is str:
            return "TEXT"
        elif python_type is int:
            return "INTEGER"
        elif python_type is float:
            return "REAL"
        elif python_type is bool:
            return "BOOLEAN"
        elif python_type is None:
            return None
        elif python_type is datetime.datetime:
            return "TIMESTAMP"
        else:
            raise ValueError(f"Unsupported type: {python_type}")

    def generate_template_schema(self) -> str:
        """Generates the full schema for all registered models."""
        schema = ""
        relations = []
        indices = []
        for model in self.models:
            schema_part, relations_new, indexes = self.generate_create_table_sql(model)
            schema += schema_part + "\n"
            relations.extend(relations_new)
            indices.extend(indexes)
        for relation in relations:
            schema += relation
        for index in indices:
            schema += index
        return schema

    def save_template_schema(self, filename="template_schema.sql"):
        """Saves the generated schema to a file."""
        schema = self.generate_template_schema()
        with open(filename, "w") as f:
            f.write(schema)
        print(f"Template schema saved to {filename}")


class MigrationGenerator:
    def __init__(
        self, migrations_path="migrations", template_schema="template_schema.sql"
    ):
        self.migrations_path = migrations_path
        self.template_schema = template_schema
        self.schema_generator = None

        # Ensure migrations folder exists
        if not os.path.exists(self.migrations_path):
            os.makedirs(self.migrations_path)
            print(f"Created migrations folder: {self.migrations_path}")

        # Ensure template schema file exists
        if not os.path.exists(self.template_schema):
            print(f"{self.template_schema} not found. Generating template schema...")
            self.generate_template_schema()

    def generate_template_schema(self):
        """Generate the template schema if it doesn't exist."""
        schema_generator = SchemaGenerator()
        schema_generator.register_all_models()  # Dynamically register all models
        schema_generator.save_template_schema(filename=self.template_schema)

    def read_template_schema(self) -> str:
        """Reads the saved template schema from the file."""
        with open(self.template_schema, "r") as f:
            return f.read()

    def generate_current_schema(self) -> str:
        """Dynamically generates the current schema based on the models."""
        schema_generator = SchemaGenerator()
        self.schema_generator = schema_generator
        schema_generator.register_all_models()  # Dynamically register all models
        return schema_generator.generate_template_schema()

    def generate_sql_operations(self, old_schema: str, new_schema: str) -> str:
        """Generates SQL operations needed to migrate from the old schema to the new schema."""
        before = parse_sql_statements(old_schema)
        after = parse_sql_statements(new_schema)
        added, removed, modified, constraints = compare_sql_statements(before, after)
        deleted_tables = [
            f"DROP TABLE IF EXISTS {t.table_name};"
            for t in removed
            if isinstance(t, DropTable)
        ]
        new_tables = [t.raw for t in added]
        table_updates = []
        for table, diffs in modified:
            for column, delta in diffs.items():
                change = None
                if delta[0] is None:
                    change = f"ALTER TABLE {table} ADD {column} {delta[1]};"
                elif delta[1] is None:
                    change = f"ALTER TABLE {table} DROP COLUMN {column};"
                else:
                    change = f"ALTER TABLE {table} ALTER COLUMN {column} {delta[1]};"
                table_updates.append(change)

        operations = deleted_tables
        operations.extend(new_tables)
        operations.extend(table_updates)
        return "\n\n".join(operations)

    def save_migration(self, migration_name: str, migration_content: str):
        """Save the generated migration file."""
        filename = f"{len(os.listdir(self.migrations_path)) + 1:03d}_migration_{migration_name}.sql"
        filepath = os.path.join(self.migrations_path, filename)
        with open(filepath, "w") as f:
            f.write(migration_content)
        print(f"Migration saved as {filename}")

    def update_template_schema(self, new_schema: str):
        """Overwrite the template_schema.sql with the new schema."""
        with open(self.template_schema, "w") as f:
            f.write(new_schema)
        print(f"Updated {self.template_schema} with the latest schema.")

    def generate_migration(self, migration_name: str):
        """Generates a migration based on schema differences and updates the template schema."""
        template_schema = self.read_template_schema()
        current_schema = self.generate_current_schema()
        if not os.listdir(self.migrations_path):
            print("No existing migrations found. Creating the initial migration.")
            self.save_migration(migration_name, template_schema)
            self.update_template_schema(current_schema)
            return

        migration_sql = self.generate_sql_operations(template_schema, current_schema)

        if migration_sql:
            self.save_migration(migration_name, migration_sql)
            self.update_template_schema(current_schema)
        else:
            print("No changes detected. Migration not created.")


class MigrationManager:
    def __init__(self, migrations_path: str = "migrations"):
        self.migrations_path = migrations_path

    def get_migration_files(self) -> List[str]:
        """Retrieve the list of migration files."""
        return sorted(
            [f for f in os.listdir(self.migrations_path) if f.endswith(".sql")]
        )

    def get_migration_hash(self, filename: str) -> str:
        """Generate a hash for a migration file."""
        filepath = os.path.join(self.migrations_path, filename)
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    async def apply_migration(self, db, migration_file: str):
        """Apply a migration to the database."""
        filepath = os.path.join(self.migrations_path, migration_file)
        with open(filepath, "r") as f:
            migration_sql = f.read()
        migration_sql_statements = parse_sql_statements(migration_sql)
        migration_hash = self.get_migration_hash(migration_file)
        print(f"RUnning migration: {migration_file} ({migration_hash})")
        for statement in migration_sql_statements:
            print(statement)
            if isinstance(statement, AlterTable):
                if statement.constraint and statement.parent_table:
                    try:
                        await db.connection.execute(statement.raw)
                    except sqlite3.OperationalError:
                        temp = await db.connection.execute(
                            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{statement.table_name}';"
                        )
                        table_sql = await temp.fetchone()
                        table_sql = (
                            table_sql[0][:-2]
                            + f",\n    FOREIGN KEY ({statement.column}) REFERENCES {statement.parent_table}({statement.parent_field})\n);"
                        )

                        await db.connection.execute(
                            f"CREATE TEMPORARY TABLE temporary AS SELECT * FROM {statement.table_name};"
                        )
                        await db.connection.execute(
                            f"DROP TABLE {statement.table_name};"
                        )
                        await db.connection.execute(table_sql)
                        await db.connection.execute(
                            f"INSERT INTO {statement.table_name} SELECT * FROM temporary;"
                        )
                        await db.connection.execute("DROP TABLE temporary;")
                elif statement.operation.startswith(
                    "ADD"
                ) or statement.operation.startswith("DROP"):
                    try:
                        await db.connection.execute(statement.raw)
                    except sqlite3.OperationalError as e:
                        if "unknown column" in str(
                            e
                        ) and "foreign key definition" in str(e):
                            print("need to drop fk constraint first")
                            column_to_drop = statement.operation.replace(
                                "DROP COLUMN ", ""
                            )
                            temp = await db.connection.execute(
                                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{statement.table_name}';"
                            )
                            table_sql = await temp.fetchone()
                            table_sql_lines = table_sql[0].split("\n")
                            table_sql_lines = [
                                line
                                for line in table_sql_lines
                                if not line.startswith(
                                    f"    FOREIGN KEY ({column_to_drop}) REFERENCES"
                                )
                            ]
                            await db.connection.execute(
                                f"CREATE TEMPORARY TABLE temporary AS SELECT * FROM {statement.table_name};"
                            )
                            await db.connection.execute(
                                f"DROP TABLE {statement.table_name};"
                            )
                            if table_sql_lines[-1] == ")" and table_sql_lines[
                                -2
                            ].endswith(","):
                                table_sql_lines[-2] = table_sql_lines[-2][:-1]
                            await db.connection.execute("\n".join(table_sql_lines))
                            await db.connection.execute(
                                f"INSERT INTO {statement.table_name} SELECT * FROM temporary;"
                            )
                            await db.connection.execute("DROP TABLE temporary;")
                            await db.connection.execute(statement.raw)

            else:
                to_apply = statement.raw
                if db.backend == "sqlite":
                    to_apply = translate_pgsql_to_sqlite(to_apply)
                await db.connection.execute(to_apply)
        await db.connection.execute(
            f"INSERT INTO migrations (migration_hash) VALUES ('{migration_hash}');"
        )
        if db.backend == "postgresql":
            await db.connection.commit()

    async def apply_pending_migrations(self, db):
        """Apply any pending migrations that haven't been applied for this customer."""
        migration_sql = (
            "CREATE TABLE IF NOT EXISTS migrations ("
            "id SERIAL PRIMARY KEY, "
            "migration_hash TEXT NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
        )
        if db.backend == "sqlite":
            migration_sql = translate_pgsql_to_sqlite(migration_sql)

        await db.connection.execute(migration_sql)

        if db.backend == "sqlite":
            result = await db.connection.execute(
                "SELECT migration_hash FROM migrations;"
            )
            applied_migrations = await result.fetchall()
            applied_migration_hashes = [m[0] for m in applied_migrations]
        elif db.backend == "postgresql":
            applied_migrations = await db.connection.fetch(
                "SELECT migration_hash FROM migrations;"
            )
            applied_migration_hashes = {
                row["migration_hash"] for row in applied_migrations
            }

        migration_files = self.get_migration_files()

        for migration_file in migration_files:
            migration_hash = self.get_migration_hash(migration_file)
            if migration_hash not in applied_migration_hashes:
                await self.apply_migration(db, migration_file)
