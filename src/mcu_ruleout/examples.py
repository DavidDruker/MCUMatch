"""Built-in example kernels (examples/index.toml), so a first run needs no code of your own."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class Example:
    name: str
    title: str
    file: str
    entry: str
    measure: str
    cflags: str
    deadline: str
    defines: dict[str, str]
    selftest: tuple[str, ...]

    @property
    def path(self) -> Path:
        return _folder() / self.file

    def source(self) -> str:
        return self.path.read_text(encoding="utf-8")


def _folder() -> Path:
    return Path(str(resources.files("mcu_ruleout").joinpath("examples")))


def all_examples() -> dict[str, Example]:
    index = tomllib.loads((_folder() / "index.toml").read_text(encoding="utf-8"))
    return {name: Example(name, e["title"], e["file"], e["entry"], e["measure"], e["cflags"], e["deadline"],
                          dict(e.get("defines", {})), tuple(e.get("selftest", ())))
            for name, e in index.items()}


def get(name: str) -> Example:
    found = all_examples()
    if name not in found:
        raise KeyError(f"unknown example {name!r}; built-in: {', '.join(found)}")
    return found[name]
