import configparser
from typing import Any, List


class Config:
    def __init__(
        self, config_file: str = None, config: dict[Any, Any] = None
    ) -> "Config":
        self._config = configparser.ConfigParser()
        if config:
            self._config.read_dict(config)
        else:
            try:
                with open(config_file, "r") as f:
                    self._config.read_file(f)
            except FileNotFoundError:
                self._config.read_dict({})

    def __getattr__(self, section: str) -> Any:
        if section in self._config:
            return _Section(self._config[section])
        raise AttributeError(f"No such section: {section}")


class _Section:
    def __init__(self, section: configparser.SectionProxy) -> None:
        self._section = section

    def __getattr__(self, key: str) -> str:
        if key in self._section:
            return self._section[key]
        raise AttributeError(f"No such key: {key}")

    @property
    def allowed_origins(self) -> List[str]:
        return [
            origin.strip()
            for origin in self._section.get("allowed_origins", "").split(",")
        ]

    @property
    def allowed_methods(self) -> str:
        return self._section.get("allowed_methods", "")

    @property
    def allowed_headers(self) -> str:
        return self._section.get("allowed_headers", "")

    @property
    def allow_credentials(self) -> str:
        return self._section.get("allow_credentials", "false")
