import datetime
import hashlib
import inspect
import os
from typing import List
from typing import Optional as TypingOptional

from .base import Model, Public
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
                        "Public": Public,
                    },
                    local_namespace,
                )

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
        elif python_type is datetime.datetime or python_type is datetime:
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

        public_statements = []
        private_statements = []

        for statement in migration_sql_statements:
            # TODO: crude check, add nuance later
            if "public." in statement.raw:
                public_statements.append(statement)
            else:
                private_statements.append(statement)

        if public_statements:
            public_applied = await self.check_migration_applied(
                db, migration_hash, public=True
            )
            if not public_applied:
                for statement in public_statements:
                    public_without_prefix = statement.raw.replace("public.", "")
                    print(f"Executing public statement: {public_without_prefix}")
                    await db.execute_in_public(public_without_prefix)
                await db.execute_in_public(
                    f"INSERT INTO migrations (migration_hash) VALUES ('{migration_hash}');"
                )

        schema_applied = await self.check_migration_applied(db, migration_hash)
        if not schema_applied:
            for statement in private_statements:
                print(f"Executing private statement: {statement.raw}")

                if isinstance(statement, AlterTable):
                    if statement.constraint and statement.parent_table:
                        await db.connection.execute(statement.raw)
                    elif statement.operation.startswith(
                        "ADD"
                    ) or statement.operation.startswith("DROP"):
                        await db.connection.execute(statement.raw)

                else:
                    to_apply = statement.raw
                    await db.connection.execute(to_apply)
            await db.connection.execute(
                f"INSERT INTO migrations (migration_hash) VALUES ('{migration_hash}');"
            )

    async def check_migration_applied(self, db, migration_hash, public=False):
        """Check if a migration has been applied."""
        if public:
            await db.execute_in_public(
                "CREATE TABLE IF NOT EXISTS migrations (id SERIAL PRIMARY KEY, migration_hash TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
            )
            result = await db.execute_in_public(
                f"SELECT * FROM migrations WHERE migration_hash = '{migration_hash}';"
            )
        else:
            await db.connection.execute(
                "CREATE TABLE IF NOT EXISTS migrations (id SERIAL PRIMARY KEY, migration_hash TEXT NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
            )
            result = await db.connection.fetch(
                f"SELECT 1 FROM migrations WHERE migration_hash = '{migration_hash}';"
            )

        return bool(result)

    async def apply_pending_migrations(self, db):
        """Apply any pending migrations that haven't been applied for this customer."""
        migration_files = self.get_migration_files()

        for migration_file in migration_files:
            await self.apply_migration(db, migration_file)
