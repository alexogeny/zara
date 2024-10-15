import datetime
import hashlib
import os
from typing import Dict, Type

from zara.utilities.database.orm import DatabaseField, Model, Public, Relationship

SQL_TYPES = ["VARCHAR", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP", "TEXT"]


def get_type_from_sql(sql: str) -> str:
    if "VARCHAR" in sql:
        return "VARCHAR"
    elif "INTEGER" in sql:
        return "INTEGER"
    elif "FLOAT" in sql:
        return "FLOAT"
    elif "BOOLEAN" in sql:
        return "BOOLEAN"
    elif "TIMESTAMP" in sql:
        return "TIMESTAMP"
    return "TEXT"


def get_length_from_sql(sql):
    if "VARCHAR" in sql:
        return sql.split("(")[1].split(")")[0]
    return None


def get_auto_increment_from_sql(sql):
    if "AUTOINCREMENT" in sql:
        return True
    return False


def get_default_from_sql(sql):
    if "DEFAULT" in sql:
        return sql.split("DEFAULT")[1].split()[0]
    return None


def SQL(x):
    return f'await conn.execute("{x}")'


def add_column(table, column_name, info):
    return SQL(f"ALTER TABLE {table} ADD COLUMN {column_name} {info}")


def add_prop(table, column_name, info):
    return SQL(f"ALTER TABLE {table} ALTER COLUMN {column_name} {info}")


def change_type(table, column, to_type):
    return SQL(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {to_type}")


def drop_column(table, column_name):
    return SQL(f"ALTER TABLE {table} DROP COLUMN {column_name}")


def drop_constraint(table, constraint):
    return SQL(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")


def drop_prop(table, field, prop):
    return SQL(f"ALTER TABLE {table} ALTER COLUMN {field} DROP {prop}")


def drop_table(table):
    return SQL(f"DROP TABLE IF EXISTS {table}")


def generate_field_modifications(model_name, field_name, field_info, prev_schema):
    ops = []

    def add_operation(operation):
        ops.append(operation)

    if field_name not in prev_schema:
        add_operation(drop_column(model_name, field_name))
        return ops

    field_type, field_length = field_info["type"], field_info.get("length", None)
    if field_length is not None:
        field_type = f"VARCHAR({field_length})"

    field_type_text = field_info["type"]

    if field_type_text != prev_schema[field_name]["type"].strip():
        if field_type not in SQL_TYPES:
            enum_data = field_info["enum"]
            enum_values = ", ".join([f"'{v.value}'" for v in enum_data])
            enum_name = f"{field_type}"
            add_operation(SQL(f"CREATE TYPE {enum_name} AS ENUM ({enum_values})"))
            field_type_text = enum_name

        add_operation(change_type(model_name, field_name, field_type_text))

    if field_info["nullable"] != prev_schema[field_name].get("nullable", True):
        if field_info["nullable"] is True:
            add_operation(drop_prop(model_name, field_name, "NOT NULL"))
        else:
            add_operation(add_prop(model_name, field_name, "NOT NULL"))

    if field_info["unique"] != prev_schema[field_name].get("unique", False):
        if field_info["unique"] is True:
            add_operation(add_prop(model_name, field_name, "UNIQUE"))
        else:
            add_operation(drop_prop(model_name, field_name, "UNIQUE"))

    new_default = field_info.get("default", None)
    old_default = prev_schema[field_name].get("default", None)
    if (
        new_default != old_default
        and not callable(new_default)
        and field_type in SQL_TYPES
    ):
        add_operation(
            f"await conn.execute('ALTER TABLE {model_name} ALTER COLUMN {field_name} SET DEFAULT {new_default}')"
        )
    elif (
        new_default != old_default
        and not callable(new_default)
        and field_type not in SQL_TYPES
    ):
        add_operation(
            f"await conn.execute(\"ALTER TABLE {model_name} ALTER COLUMN {field_name} SET DEFAULT '{new_default.value}'\")"
        )

    if field_info["primary_key"] != prev_schema[field_name].get("primary_key", False):
        if field_info["primary_key"] is True:
            add_operation(add_prop(model_name, field_name, "ADD PRIMARY KEY"))
        else:
            add_operation(drop_prop(model_name, field_name, "ADD PRIMARY KEY"))

    return ops


class MigrationGenerator:
    def __init__(self, migrations_dir: str, models: Dict[str, Type[Model]]):
        self.migrations_dir = migrations_dir
        self.models = models
        self.current_state = self.get_current_state()
        self.current_public_state = self.get_current_state(public=True)

    def get_model_by_table_name(self, table_name):
        for model_name, model_class in self.models.items():
            if model_class._table_name == table_name:
                return model_class

    def check_if_migration_exists(self, hash_value):
        if not os.path.exists(self.migrations_dir):
            return False
        migration_files = sorted(
            [f for f in os.listdir(self.migrations_dir) if f.endswith(".migration.py")]
        )
        for migration_file in migration_files:
            if hash_value in migration_file:
                return True
        return False

    def generate_migration(self, name: str, schemas: list[str]):
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M")
        hash_value = hashlib.md5(name.encode()).hexdigest()[:8]
        if self.check_if_migration_exists(hash_value):
            raise ValueError(f"Migration with hash {hash_value} already exists.")
        filename = f"{timestamp}_{hash_value}_{name}.migration.py"
        filepath = os.path.join(self.migrations_dir, filename)

        cumulative_state, public_cumulative_state = self.get_cumulative_state()
        current_state = self.current_state
        public_current_state = self.current_public_state

        up_ops, up_pre_ops, up_post_ops = self.generate_upgrade_operations(
            cumulative_state, current_state, public=False
        )
        public_up_ops, public_up_pre_ops, public_up_post_ops = (
            self.generate_upgrade_operations(
                public_cumulative_state, public_current_state, public=True
            )
        )
        down_ops, down_pre_ops, down_post_ops = self.generate_downgrade_operations(
            cumulative_state, current_state, public=False
        )
        public_down_ops, public_down_pre_ops, public_down_post_ops = (
            self.generate_downgrade_operations(
                public_cumulative_state, public_current_state, public=True
            )
        )

        if not os.path.exists(self.migrations_dir):
            os.makedirs(self.migrations_dir)

        with open(filepath, "w") as f:
            f.write(f"SCHEMAS = {schemas}\n\n")
            f.write("async def upgrade(conn):\n")
            self.write_ops(f, [up_pre_ops, up_ops, up_post_ops])
            f.write("\n")
            f.write("async def downgrade(conn):\n")
            self.write_ops(f, [down_pre_ops, down_ops, down_post_ops])
            f.write("async def public_upgrade(conn):\n")
            self.write_ops(f, [public_up_pre_ops, public_up_ops, public_up_post_ops])
            f.write("\n")
            f.write("async def public_downgrade(conn):\n")
            self.write_ops(
                f, [public_down_pre_ops, public_down_ops, public_down_post_ops]
            )

        return filename

    @staticmethod
    def write_ops(handler, ops):
        for set_of_ops in ops:
            for op in set_of_ops:
                handler.write(f"    {op}\n")

    def get_current_state(self, public=False):
        current_state = {}
        for model_name, model_class in self.models.items():
            if not issubclass(model_class, Public) and not public:
                current_state[model_class._table_name] = self.get_model_schema(
                    model_class
                )
            elif issubclass(model_class, Public) and public:
                current_state[model_class._table_name] = self.get_model_schema(
                    model_class
                )
        return current_state

    def get_cumulative_state(self):
        cumulative_state = {}
        public_cumulative_state = {}
        if not os.path.exists(self.migrations_dir):
            return cumulative_state, public_cumulative_state
        migration_files = sorted(
            [f for f in os.listdir(self.migrations_dir) if f.endswith(".migration.py")]
        )

        for migration_file in migration_files:
            module_path = os.path.join(self.migrations_dir, migration_file)

            with open(module_path, "r") as file:
                code = file.read()
                module_globals = {}
                exec(code, module_globals)
                module_globals["__source__"] = code

            ops = self.parse_upgrade_operations(module_globals["__source__"])
            upgrade_ops = ops["upgrade"]
            public_upgrade_ops = ops["public_upgrade"]
            cumulative_state = self.apply_operations(cumulative_state, upgrade_ops)
            public_cumulative_state = self.apply_operations(
                public_cumulative_state, public_upgrade_ops
            )

        return cumulative_state, public_cumulative_state

    def parse_upgrade_operations(self, upgrade_func):
        import ast

        tree = ast.parse(upgrade_func)
        operations = {}

        class UpgradeVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_func = None

            def visit_AsyncFunctionDef(self, node):
                self.current_func = node.name
                operations[self.current_func] = []
                self.generic_visit(node)

            def visit_Await(self, node):
                if (
                    self.current_func
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                ):
                    if node.value.func.attr == "execute":
                        sql = ast.literal_eval(node.value.args[0])
                        operations[self.current_func].append(sql)
                self.generic_visit(node)

        visitor = UpgradeVisitor()
        visitor.visit(tree)

        return operations

    def apply_operations(self, state, operations):
        for op in operations:
            if op.startswith("CREATE TABLE"):
                table_name = op.split()[2]
                state[table_name] = {}
                for column in op.split("\n")[1:-1]:
                    txt = column.strip(",").strip()
                    column_name = txt.split()[0]
                    result = {
                        "type": get_type_from_sql(txt),
                        "primary_key": "PRIMARY KEY" in txt,
                        "nullable": "NOT NULL" not in txt,
                        "default": None,
                        "unique": "UNIQUE" in txt,
                    }
                    state[table_name][column_name] = result
            elif op.startswith("ALTER TABLE"):
                parts = op.split()
                table_name = parts[2]
                if "ADD COLUMN" in op:
                    column_name = parts[5]
                    column_type = " ".join(parts[6:])
                    state[table_name][column_name] = {"type": column_type}
                elif "DROP COLUMN" in op:
                    column_name = parts[5]
                    del state[table_name][column_name]
                elif "ADD CONSTRAINT" in op:
                    constraint_type = parts[6:7]
                    if "FOREIGN KEY" in constraint_type:
                        tbl, _ = parts[10].strip(")").split("(")
                        tbl_cls = self.get_model_by_table_name(tbl)()
                        result = {
                            "type": tbl_cls._table_name,
                            "primary_key": tbl_cls._table_name.lower() + "_id",
                            "nullable": False,
                            "default": None,
                            "unique": False,
                        }
                        state[table_name][column_name] = result

        return state

    def get_model_schema(self, model_class):
        schema = {}
        model = model_class()
        combined_model_fields = {
            **model_class.__dict__,
            **model._get_mro_fields(),
        }
        for name, field in combined_model_fields.items():
            if name.startswith("_"):
                continue
            if isinstance(field, DatabaseField):
                schema[name] = {
                    "type": field.data_type,
                    "primary_key": field.primary_key,
                    "nullable": field.nullable,
                    "default": field.default,
                    "unique": field.unique,
                    "relation": False,
                    "enum": field.get_enum(),
                }
            elif isinstance(field, Relationship):
                column_name = field._sql_column_name()
                if column_name is not None:
                    schema[column_name] = {
                        "type": field.data_type,
                        "primary_key": False,
                        "nullable": True,
                        "default": None,
                        "unique": False,
                        "relation": True,
                        "relation_name": field.as_fkname(model._table_name),
                    }
        return schema

    def generate_upgrade_operations(self, previous_state, current_state, public=False):
        ops, pre_ops, post_ops = [], [], []
        for model_name, current_schema in current_state.items():
            model = self.get_model_by_table_name(model_name)()
            if model_name not in previous_state:
                ops.append(f"await conn.execute('''{model._get_table_sql()}''')")
                for operation in model._get_relation_constraints():
                    post_ops.append(SQL(operation))
                for operation in model._get_indexes():
                    post_ops.append(SQL(operation))
            else:
                prev_schema = previous_state[model_name]
                for field_name, field_info in current_schema.items():
                    if field_name not in prev_schema:
                        if field_info.get("relation", False) is False:
                            ops.append(
                                add_column(model_name, field_name, field_info["type"])
                            )
                        elif field_name not in prev_schema:
                            ops.append(
                                add_column(model_name, field_name, "VARCHAR(30)")
                            )
                            relname = field_info.get("relation_name")
                            fkop = next(
                                (
                                    x
                                    for x in model._get_relation_constraints()
                                    if relname in x and field_name in x
                                ),
                                None,
                            )
                            if fkop:
                                post_ops.append(SQL(fkop))
                    elif field_name in prev_schema and field_name not in current_schema:
                        if field_info.get("relation", False) is False:
                            ops.append(drop_column(model_name, field_name))
                        elif field_name not in prev_schema:
                            ops.append(drop_column(model_name, field_name))
                    else:
                        ops.extend(
                            generate_field_modifications(
                                model_name, field_name, field_info, prev_schema
                            )
                        )

        if not ops and not post_ops:
            return ["pass"], [], []
        return ops, pre_ops, post_ops

    def generate_downgrade_operations(
        self, previous_state, current_state, public=False
    ):
        operations, pre_ops, post_ops = [], [], []
        for model_name, current_schema in current_state.items():
            if model_name not in previous_state:
                for field_name in current_schema:
                    field = current_schema[field_name]
                    if field.get("relation", False) is True:
                        fk_name = field.get("relation_name")
                        pre_ops.append(drop_constraint(model_name, fk_name))
                operations.append(drop_table(model_name))
            else:
                previous_schema = previous_state.get(model_name, {})
                for field_name in current_schema:
                    if field_name not in previous_schema:
                        field = current_schema[field_name]
                        if field.get("relation", False) is True:
                            fk_name = field.get("relation_name")
                            pre_ops.append(drop_constraint(model_name, fk_name))
                        operations.extend(
                            generate_field_modifications(
                                model_name, field_name, field, previous_schema
                            )
                        )
        if not operations:
            return ["pass"], [], []
        return operations, pre_ops, post_ops

    def get_latest_migration(self):
        migrations = sorted(os.listdir(self.migrations_dir))
        return migrations[-1] if migrations else None

    def update_model_states(self, current_state):
        latest_migration = self.get_latest_migration()
        if latest_migration:
            self.model_states[latest_migration] = current_state
