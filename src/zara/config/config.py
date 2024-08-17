import configparser
from typing import Any


class Config:
    _instance = None
    _config = configparser.ConfigParser()

    def __new__(cls, config_file: str = "config.ini") -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._config.read(config_file)
        return cls._instance

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


config = Config()
