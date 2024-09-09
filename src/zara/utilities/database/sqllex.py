import re
from typing import Dict, List, Optional, Tuple


# Define classes to represent SQL statements
class SQLStatement:
    def __init__(self, table_name: str, raw: str):
        self.table_name = table_name
        self.raw = raw

    def __eq__(self, other):
        if isinstance(other, SQLStatement):
            return (
                self.table_name == other.table_name and self.__dict__ == other.__dict__
            )
        return False

    def __repr__(self):
        return f"<{self.__class__.__name__} table={self.table_name}>"


class DropTable(SQLStatement):
    def __init__(self, table_name: str, raw: str):
        super().__init__(table_name, raw)


class CreateTable(SQLStatement):
    def __init__(self, table_name: str, raw: str, columns: Dict[str, str]):
        super().__init__(table_name, raw)
        self.columns = (
            columns  # Store columns as a dictionary {column_name: column_definition}
        )

    def __eq__(self, other):
        return super().__eq__(other) and self.columns == other.columns

    def __repr__(self):
        return f"<CreateTable table={self.table_name}, columns={self.columns}>"


class AlterTable(SQLStatement):
    def __init__(
        self,
        table_name: str,
        raw: str,
        operation: str,
        column: Optional[str] = None,
        constraint: Optional[str] = None,
        parent_table: Optional[str] = None,
        parent_field: Optional[str] = None,
    ):
        super().__init__(table_name, raw)
        self.operation = operation
        self.column = column
        self.constraint = constraint
        self.parent_table = parent_table
        self.parent_field = parent_field

    def __repr__(self):
        return f"<AlterTable table={self.table_name}, operation={self.operation}, column={self.column}, constraint={self.constraint} on={self.parent_table}({self.parent_field})>"


# Function to parse SQL statements
def parse_sql_statements(sql_content: str) -> List[SQLStatement]:
    # Patterns to match SQL statements
    drop_pattern = r"DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+);"
    create_pattern = r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\);"
    alter_pattern = r"ALTER\s+TABLE\s+(\w+)\s+(.*?);"

    statements = []

    # Match and parse DROP TABLE
    for match in re.finditer(drop_pattern, sql_content, re.IGNORECASE):
        table_name = match.group(1)
        statements.append(DropTable(table_name, match.group(0)))

    # Match and parse CREATE TABLE
    for match in re.finditer(create_pattern, sql_content, re.IGNORECASE | re.DOTALL):
        table_name = match.group(1)
        columns_content = match.group(2)
        columns = parse_columns(columns_content)  # Parse column definitions
        statements.append(CreateTable(table_name, match.group(0), columns))

    # Match and parse ALTER TABLE
    for match in re.finditer(alter_pattern, sql_content, re.IGNORECASE | re.DOTALL):
        table_name = match.group(1)
        operation = match.group(2)
        # Look for foreign key constraints in the operation
        if "ADD CONSTRAINT" in operation and "FOREIGN KEY" in operation:
            constraint_match = re.search(
                r"ADD CONSTRAINT\s+(\w+)\s+FOREIGN KEY", operation, re.IGNORECASE
            )
            column_match = re.search(r"\((.*?)\)", operation)
            reference_match = re.search(r"REFERENCES\s(\w+)\((\w+)\)", operation)
            if constraint_match and column_match:
                constraint = constraint_match.group(1)
                column = column_match.group(1)
                statements.append(
                    AlterTable(
                        table_name,
                        match.group(0),
                        "ADD FOREIGN KEY",
                        column=column,
                        constraint=constraint,
                        parent_table=reference_match.group(1),
                        parent_field=reference_match.group(2),
                    )
                )
        else:
            # For other alter operations, just store the operation without parsing further
            statements.append(AlterTable(table_name, match.group(0), operation))

    return statements


# Helper function to parse column definitions
def parse_columns(columns_content: str) -> Dict[str, str]:
    columns = {}
    column_defs = columns_content.split(",")
    for column_def in column_defs:
        column_def = column_def.strip()
        if " " in column_def:
            column_name, column_type = column_def.split(" ", 1)
            columns[column_name.strip()] = column_type.strip()
    return columns


# Function to compare two lists of SQL statements
def compare_sql_statements(
    before_statements: List[SQLStatement], after_statements: List[SQLStatement]
):
    added = []
    removed = []
    modified = []
    constraints = []

    # Detect added and removed statements
    before_dict = {
        stmt.table_name: stmt
        for stmt in before_statements
        if isinstance(stmt, CreateTable)
    }
    after_dict = {
        stmt.table_name: stmt
        for stmt in after_statements
        if isinstance(stmt, CreateTable)
    }
    before_alter = {
        stmt.table_name: stmt
        for stmt in before_statements
        if isinstance(stmt, AlterTable)
    }
    after_alter = {
        stmt.table_name: stmt
        for stmt in after_statements
        if isinstance(stmt, AlterTable)
    }

    before_tables = set(before_dict.keys())
    after_tables = set(after_dict.keys())
    before_alters = set(before_dict.keys())
    after_alters = set(after_dict.keys())

    added_tables = after_tables - before_tables
    removed_tables = before_tables - after_tables

    added_alters = after_alters - before_alters
    removed_alters = before_alters - after_alters

    # Add to the added and removed lists
    for table in added_tables:
        added.append(after_dict[table])
    for alter in added_alters:
        added.append(after_alter[alter])

    for table in removed_tables:
        removed.append(before_dict[table])
    for alter in removed_alters:
        removed.append(before_alter[alter])
    intersection = before_tables.intersection(after_tables)
    # Check for modified statements (same table, different content)
    for table in intersection:
        before_table = before_dict[table]
        after_table = after_dict[table]
        if isinstance(before_table, CreateTable) and isinstance(
            after_table, CreateTable
        ):
            # Compare column definitions
            column_diffs = compare_columns(before_table.columns, after_table.columns)
            if column_diffs:
                modified.append(
                    (table, column_diffs)
                )  # Pass the table name and column differences
        elif before_table != after_table:
            modified.append((table, {}))

    return added, removed, modified, constraints


def compare_columns(
    before_columns: Dict[str, str], after_columns: Dict[str, str]
) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    diffs = {}

    before_set = set(before_columns.keys())
    after_set = set(after_columns.keys())
    added_columns = after_set - before_set
    removed_columns = before_set - after_set
    common_columns = before_set.intersection(after_set)

    for column in added_columns:
        diffs[column] = (
            None,
            after_columns[column],
        )  # None means the column didn't exist before

    for column in removed_columns:
        diffs[column] = (
            before_columns[column],
            None,
        )  # None means the column was removed

    for column in common_columns:
        if before_columns[column] != after_columns[column]:
            diffs[column] = (before_columns[column], after_columns[column])

    return diffs
