import argparse
import asyncio

from zara.utilities.database import AsyncDatabase
from zara.utilities.database.migrations import MigrationGenerator, MigrationManager


def create_migration(migration_name: str):
    """Create a new migration file by comparing the current schema to the template."""
    migration_generator = MigrationGenerator()
    migration_generator.generate_migration(migration_name)


async def apply_migrations(customer_name: str):
    """Apply pending migrations for a specific customer."""
    async with AsyncDatabase(customer_name, backend="postgresql") as db:
        migration_manager = MigrationManager()
        await migration_manager.apply_pending_migrations(db)


async def handle_new_customer(customer_name: str):
    """Register a new customer and apply all necessary migrations."""
    async with AsyncDatabase(customer_name, backend="postgresql") as db:
        if db.backend == "postgresql":
            await db.connection.execute(f"CREATE SCHEMA IF NOT EXISTS {customer_name};")
            await db.connection.execute(f"SET search_path TO {customer_name};")

        migration_manager = MigrationManager()
        await migration_manager.apply_pending_migrations(db)

        print(f"Customer {customer_name} registered and migrations applied.")


def main():
    parser = argparse.ArgumentParser(description="Migration Manager CLI")

    parser.add_argument("--create", type=str, help="Create a new migration")

    parser.add_argument(
        "--apply", type=str, help="Apply migrations for a specific customer"
    )

    parser.add_argument(
        "--register", type=str, help="Register a new customer and apply migrations"
    )

    args = parser.parse_args()

    if args.create:
        create_migration(args.create)

    elif args.apply:
        asyncio.run(apply_migrations(args.apply))

    elif args.register:
        asyncio.run(handle_new_customer(args.register))


if __name__ == "__main__":
    main()
