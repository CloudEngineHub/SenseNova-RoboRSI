# Copyright 2026 The RoboRSI Contributors.
# Licensed under the Apache License, Version 2.0.

"""Load harness system prompts with shared manipulation notes."""

from pathlib import Path


def load_system_prompt(path: Path) -> str:
    """Append the shared notes to a built-in or custom system prompt."""
    system = Path(path).read_text(encoding="utf-8").rstrip()
    notes = Path(__file__).with_name("note.md").read_text(encoding="utf-8").strip()
    return f"{system}\n\n{notes}\n"
