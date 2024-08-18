import re


def camel_to_snake(name: str) -> str:
    # Convert CamelCase to snake_case
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return name
