#!/usr/bin/env python3
"""Dry-run by default; --confirm imports validated CSV rows with an audit trail."""
import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3

FIELDS = ("name", "email", "phone", "kind", "source", "stage", "next_follow_up", "notes")
STAGES = {"New", "Contacted", "Qualified", "Proposal", "Won", "Lost"}


def inspect(path):
    accepted, rejected = [], []
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise ValueError("CSV needs a name column")
        for number, raw in enumerate(reader, 2):
            row = {key: (raw.get(key) or "").strip() for key in FIELDS}
            row["kind"] = row["kind"] or "lead"
            row["stage"] = row["stage"] or "New"
            if not 1 <= len(row["name"]) <= 120 or row["kind"] not in {"lead", "buyer", "seller"} or row["stage"] not in STAGES or any(len(row[k]) > cap for k, cap in (("email", 200), ("phone", 40), ("source", 120), ("notes", 2000))):
                rejected.append(number)
            else:
                accepted.append(row)
    return accepted, rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    accepted, rejected = inspect(args.csv)
    print(json.dumps({"accepted": len(accepted), "rejected": rejected, "dry_run": not args.confirm}))
    if args.confirm and not rejected:
        db = sqlite3.connect(Path(os.environ.get("TOOL_DATA", "/data")) / "tool.db")
        with db:
            for row in accepted:
                cursor = db.execute("INSERT INTO contacts(name,email,phone,kind,source,stage,next_follow_up,notes) VALUES (?,?,?,?,?,?,?,?)", tuple(row[k] for k in FIELDS))
                db.execute("INSERT INTO audit(actor,action,entity,entity_id,detail) VALUES (?,?,?,?,?)", ("client", "csv-import", "contact", cursor.lastrowid, ""))
        db.close()
    elif args.confirm and rejected:
        raise ValueError("Rejected rows must be fixed before import")


if __name__ == "__main__":
    main()
