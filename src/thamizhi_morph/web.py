from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def playground_html() -> str:
    return (
        files("thamizhi_morph")
        .joinpath("static", "index.html")
        .read_text(encoding="utf-8")
    )
