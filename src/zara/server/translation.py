import json
from pathlib import Path
from typing import Any


class I18n:
    def __init__(self, app, i18n_folder="i18n"):
        self.app = app
        self.app._translations = self.load_translations(i18n_folder)

    def load_translations(self, folder):
        results = {}
        for path in Path(folder).glob("*.*"):
            language = path.stem
            with path.open() as f:
                if path.suffix == ".json":
                    results[language] = json.load(f)
        return results

    def get_translator(self, language: str):
        def t(key: str, count: Any = None, **kwargs) -> str:
            keys = key.split(".")
            translation = self.app._translations.get(language, {})
            for k in keys:
                translation = translation.get(k, {})
            if not translation:
                raise ValueError(f"translation with key {key} does not exist")
            if isinstance(translation, dict) and count is not None:
                count = int(count)
                if count == 0:
                    translation = translation.get("zero", translation.get("many"))
                elif count == 1:
                    translation = translation.get("one", translation.get("many"))
                elif count < 5:
                    translation = translation.get("few", translation.get("many"))
                else:
                    translation = translation.get("many")
                return translation.format(count=count, **kwargs)
            return translation

        return t
