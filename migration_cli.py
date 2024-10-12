import argparse
import asyncio
import datetime
import hashlib
import os

from migrate import Migrator


async def main():
    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument(
        "--initial", action="store_true", help="Create initial migration"
    )
    parser.add_argument("--generate", metavar="NAME", help="Generate a new migration")
    parser.add_argument("--manual", metavar="NAME", help="Create a manual migration")

    args = parser.parse_args()

    migrator = Migrator()
    migrator.collect_models()

    if args.initial:
        filename = migrator.generate_migration("initial", [])
        print(f"Generated initial migration: {filename}")

    elif args.generate:
        filename = migrator.generate_migration(args.generate, ["public"])
        print(f"Generated new migration: {filename}")

    elif args.manual:
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
        hash_value = hashlib.md5(args.manual.encode()).hexdigest()[:8]
        filename = f"{timestamp}_{hash_value}_{args.manual}.migration.py"
        filepath = os.path.join(migrator.migrations_dir, filename)

        with open(filepath, "w") as f:
            f.write("SCHEMAS = ['public']\n\n")
            f.write("async def upgrade(conn):\n")
            f.write("    # TODO: Add your upgrade operations here\n")
            f.write("    pass\n\n")
            f.write("async def downgrade(conn):\n")
            f.write("    # TODO: Add your downgrade operations here\n")
            f.write("    pass\n")

        print(f"Created manual migration: {filename}")

    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
