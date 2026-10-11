"""Settings, read from workboard.toml at the top of the project (all optional)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

FILE = "workboard.toml"


@dataclass
class Config:
    root: str = "."
    board: str = "WORK.md"
    title: str = ""
    remote: str = "origin"
    branch: str = "main"
    who: str = ""
    repo_url: str = ""
    stale_days: int = 2
    decision_areas: list[str] = field(default_factory=lambda: ["humans"])
    done_heading: str = "Done"
    log_heading: str = "Changes to the board"

    @property
    def board_path(self) -> str:
        return os.path.join(self.root, self.board)


def find_root(start: str = ".") -> str:
    """The nearest folder, going up, that holds workboard.toml or .git."""
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, FILE)) or os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start)
        d = parent


def load(start: str = ".") -> Config:
    cfg = Config(root=find_root(start))
    path = os.path.join(cfg.root, FILE)
    if tomllib and os.path.exists(path):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for key, value in data.items():
            if hasattr(cfg, key) and key != "root":
                setattr(cfg, key, value)
    if not cfg.title:
        cfg.title = os.path.basename(cfg.root)
    return cfg
