from zara.errors import ValidationError


def validate_slug(value):
    if not isinstance(value, str):
        raise ValidationError(f"Slug is not a string: {value}")
    if len(value) > 255:
        raise ValidationError(f"Slug is too long: {value}")
    if not value.isupper():
        raise ValidationError(f"Slug is not uppercase: {value}")
    if " " in value or "-" in value:
        raise ValidationError(f"Slug contains spaces or hyphens: {value}")
    if any(char.isdigit() for char in value):
        raise ValidationError(f"Slug contains digits: {value}")
    return True


def validate_username(value):
    if not isinstance(value, str):
        raise ValidationError(f"Username is not a string: {value}")
    if len(value) > 255:
        raise ValidationError(f"Username is too long: {value}")
    if not value.islower():
        raise ValidationError(f"Username is not lowercase: {value}")
    if " " in value or "-" in value:
        raise ValidationError(f"Username contains spaces or hyphens: {value}")
    return True
