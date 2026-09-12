"""Build images from a committed checkout; never start services or deploy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_environment(root: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        # Fixed Git operations below; argv only, no shell or source-derived commands.
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()  # noqa: S603, S607

    if git("status", "--porcelain", "--untracked-files=normal"):
        raise SystemExit("Commit or preserve working-tree changes before building release images.")
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    frontend = json.loads((root / "frontend/package.json").read_text())["version"]
    if version != frontend:
        raise SystemExit("Frontend and project versions differ; run scripts/release_contract.py.")
    return {
        **os.environ,
        "ACKB_BUILD_GIT_SHA": git("rev-parse", "HEAD"),
        "ACKB_APP_VERSION": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", "-f", action="append", default=[])
    parser.add_argument("--env-file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("services", nargs="*", default=["backend", "frontend", "reverse-proxy"])
    args = parser.parse_args()
    environment = build_environment(ROOT)
    command = ["docker", "compose"]
    if args.env_file:
        command.extend(["--env-file", args.env_file])
    for filename in args.file:
        command.extend(["--file", filename])
    command.extend(["build", *args.services])
    print(
        json.dumps(
            {
                "version": environment["ACKB_APP_VERSION"],
                "commit": environment["ACKB_BUILD_GIT_SHA"],
                "command": command,
            }
        ),
        flush=True,
    )
    if not args.dry_run:
        # Explicit operator CLI arguments, never evaluated through a shell.
        subprocess.run(command, cwd=ROOT, env=environment, check=True)  # noqa: S603


if __name__ == "__main__":
    main()
