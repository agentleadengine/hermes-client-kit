"""Read the launcher path shared with shell callers."""

from pathlib import Path

HERMES_BIN = Path(__file__).with_name("hermes-path.conf").read_text().strip().split("=", 1)[1]
