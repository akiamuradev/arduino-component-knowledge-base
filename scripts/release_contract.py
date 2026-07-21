from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(label: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def main() -> None:
    project = tomllib.loads(read("pyproject.toml"))["project"]
    version = project["version"]
    failures: list[str] = []

    frontend_package = json.loads(read("frontend/package.json"))
    frontend_lock = json.loads(read("frontend/package-lock.json"))
    uv_packages = tomllib.loads(read("uv.lock"))["package"]
    locked_project = next(
        package for package in uv_packages if package["name"] == "arduino-component-knowledge-base"
    )

    exact_values = {
        "backend __version__": re.search(
            r'__version__ = "([^"]+)"', read("src/arduino_component_kb/__init__.py")
        ),
        "backend config default": re.search(
            r'app_version: str = "([^"]+)"', read("src/arduino_component_kb/config.py")
        ),
    }
    for label, match in exact_values.items():
        require(label, match is not None and match.group(1) == version, failures)

    require("frontend package version", frontend_package["version"] == version, failures)
    require("frontend Node range", frontend_package["engines"]["node"] == ">=22.12 <26", failures)
    require("frontend lock root version", frontend_lock["version"] == version, failures)
    require(
        "frontend lock package version",
        frontend_lock["packages"][""]["version"] == version,
        failures,
    )
    require("uv project version", locked_project["version"] == version, failures)

    expected_fragments = {
        "README.md": [f"version **{version}**", f"версия — **{version}**"],
        ".env.example": [f"ACKB_APP_VERSION={version}"],
        ".env.production.example": [f"ACKB_APP_VERSION={version}"],
        "compose.yaml": [
            f"backend:{version}",
            f"frontend:{version}",
            f"reverse-proxy:{version}",
            f"ACKB_APP_VERSION:-{version}",
        ],
        "frontend/Dockerfile": [f"ARG VITE_APP_VERSION={version}"],
        "frontend/README.md": [f"VITE_APP_VERSION={version}"],
        "frontend/src/config/brand.ts": [f'VITE_APP_VERSION, "{version}"'],
        "CHANGELOG.md": [f"## [{version}]"],
    }
    for path, fragments in expected_fragments.items():
        contents = read(path)
        for fragment in fragments:
            require(f"{path}: {fragment}", fragment in contents, failures)

    workflow = read(".github/workflows/quality.yml")
    action_refs = re.findall(r"uses:\s+([^\s#]+)", workflow)
    require("workflow contains actions", bool(action_refs), failures)
    for action_ref in action_refs:
        require(
            f"immutable action ref: {action_ref}",
            re.fullmatch(r"[^@]+@[0-9a-f]{40}", action_ref) is not None,
            failures,
        )

    require("runtime requirements lock", "--hash=sha256:" in read("requirements.lock"), failures)

    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise SystemExit(f"Release contract failed for {version}:\n{details}")
    print(f"Release contract passed for {version}.")


if __name__ == "__main__":
    main()
