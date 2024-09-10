import os


class EnvLoader:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(EnvLoader, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, filepath=None):
        if not self._initialized:
            if filepath is None:
                filepath = os.path.join(os.getcwd(), ".env")

            self._env_vars = {}
            self._load_dotenv(filepath)
            self._set_attrs()
            self._initialized = True

    def _load_dotenv(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"{filepath} not found.")

        with open(filepath) as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    self._env_vars[key] = value
                    os.environ[key] = value

    def _set_attrs(self):
        for key, value in self._env_vars.items():
            setattr(self, key, value)

    def _cast_bool(self, value):
        return value.lower() in ["true", "1", "yes"]

    def get(self, key, default=None, required=False, cast_type=None):
        if key in self._env_vars:
            value = self._env_vars[key]
        elif key in os.environ:
            value = os.environ[key]
        else:
            if required:
                raise ValueError(f"Required environment variable '{key}' is missing.")
            return default

        if cast_type is bool:
            return self._cast_bool(value)

        if cast_type:
            try:
                value = cast_type(value)
            except ValueError:
                raise ValueError(
                    f"Environment variable '{key}' cannot be cast to {cast_type.__name__}."
                )

        return value


env = EnvLoader()
