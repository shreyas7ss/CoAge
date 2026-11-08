"""Prompt template loader (versioned by content hash)."""

import hashlib
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> tuple[str, str]:
    """Return ``(text, version_hash)`` for ``prompts/{name}.md``."""
    path = _PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()
