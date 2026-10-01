"""Create a reviewed local-only Hermes cron draft job."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from hermes_runtime import HERMES_BIN

ETC = Path("/etc/hermes-kit")
HOME = Path("/home/hermes/.hermes/profiles/client")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schedule")
    parser.add_argument("prompt")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError("Run as root with the client present")
    ledger = json.loads((ETC / "consents.json").read_text())
    if not any(x.get("integration") == "schedules" for x in ledger.get("consents", [])):
        raise ValueError("Schedules power-up is off")
    if not 1 <= len(args.name) <= 80 or not 1 <= len(args.prompt) <= 4000:
        raise ValueError("Invalid schedule name or prompt")
    from kit_powerup import validate_cron_jobs
    validate_cron_jobs()
    path = HOME / "cron" / "jobs.json"
    before = json.loads(path.read_text()) if path.exists() else []
    before = before if isinstance(before, list) else before.get("jobs", [])
    created = subprocess.run(["runuser", "-u", "hermes", "--", "env", "HOME=/home/hermes", "HERMES_HOME=/home/hermes/.hermes", HERMES_BIN, "-p", "client", "cron", "create", args.schedule, args.prompt, "--name", args.name, "--deliver", "local"], capture_output=True, text=True, check=False)
    print(created.stdout, end="")
    print(created.stderr, end="", file=sys.stderr)
    validate_cron_jobs()
    after = json.loads(path.read_text())
    after = after if isinstance(after, list) else after.get("jobs", [])
    old_ids = {str(x.get("id")) for x in before}
    new_ids = [str(x.get("id")) for x in after if str(x.get("id")) not in old_ids]
    if len(new_ids) != 1:
        if created.returncode:
            raise subprocess.CalledProcessError(created.returncode, created.args, created.stdout, created.stderr)
        raise ValueError("Cron creation did not produce exactly one reviewed job")
    ids_path = ETC / "schedules-ids.json"
    ids = json.loads(ids_path.read_text()) if ids_path.exists() else []
    ids.extend(new_ids)
    ids_path.write_text(json.dumps(ids) + "\n")
    ids_path.chmod(0o600)
    if created.returncode:
        print("Job was created and reviewed, but Hermes reported that the scheduler is not ready.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
