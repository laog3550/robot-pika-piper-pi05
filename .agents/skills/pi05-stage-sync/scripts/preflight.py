#!/usr/bin/env python3
"""Read-only publication checks for the PI05 deployment repository."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlparse


EXPECTED_REPOSITORY = "laog3550/robot-pika-piper-pi05"
GENERATED_PARTS = {"build", "devel", "install", "logs", "__pycache__", ".pytest_cache"}
GENERATED_SUFFIXES = (".bag", ".bag.active", ".log", ".pyc", ".pyo")
SENSITIVE_NAMES = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "pi05.env"}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def repository_from_remote(remote: str) -> str | None:
    remote = remote.strip()
    if remote.startswith("git@github.com:"):
        path = remote.split(":", 1)[1]
    elif remote.startswith("ssh://git@github.com/"):
        path = urlparse(remote).path.lstrip("/")
    elif remote.startswith("https://github.com/") or remote.startswith("http://github.com/"):
        path = urlparse(remote).path.lstrip("/")
    else:
        return None
    return re.sub(r"\.git/?$", "", path).strip("/")


def changed_paths(repo: Path) -> list[str]:
    result = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = result.stdout.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        paths.append(entry[3:])
        if "R" in status or "C" in status:
            if index < len(entries) and entries[index]:
                paths.append(entries[index])
                index += 1
    return sorted(set(paths))


def read_scope(path: Path) -> tuple[set[str], list[str]]:
    scope: set[str] = set()
    errors: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        candidate = PurePosixPath(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            errors.append(f"scope line {number} is not repository-relative: {value}")
            continue
        scope.add(candidate.as_posix())
    if not scope:
        errors.append("scope file contains no paths")
    return scope, errors


def unsafe_reason(path: str) -> str | None:
    candidate = PurePosixPath(path)
    if any(part in GENERATED_PARTS for part in candidate.parts):
        return "generated/cache directory"
    lowered = candidate.name.lower()
    if lowered in SENSITIVE_NAMES or lowered.endswith(SENSITIVE_SUFFIXES):
        if not lowered.endswith((".example", ".example.env")):
            return "sensitive filename"
    if lowered.endswith(GENERATED_SUFFIXES):
        return "generated/runtime artifact"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".", help="repository root")
    parser.add_argument("--mode", choices=("start", "publish"), default="start")
    parser.add_argument("--scope-file", type=Path)
    parser.add_argument("--expected-repository", default=EXPECTED_REPOSITORY)
    args = parser.parse_args()

    requested = Path(args.repo).resolve()
    report: dict[str, object] = {
        "ok": False,
        "mode": args.mode,
        "expected_repository": args.expected_repository,
        "errors": [],
        "warnings": [],
    }
    errors = report["errors"]
    warnings = report["warnings"]
    assert isinstance(errors, list) and isinstance(warnings, list)

    top = git(requested, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        errors.append(f"not a git repository: {requested}")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    repo = Path(top.stdout.strip()).resolve()
    report["repository_root"] = str(repo)
    if repo != requested:
        errors.append(f"path is not the repository root: {requested}")

    remote = git(repo, "remote", "get-url", "origin", check=False)
    origin = remote.stdout.strip() if remote.returncode == 0 else ""
    actual_repository = repository_from_remote(origin)
    report["origin"] = origin
    report["actual_repository"] = actual_repository
    if actual_repository != args.expected_repository:
        errors.append(
            f"origin identifies {actual_repository!r}, expected {args.expected_repository!r}"
        )

    head = git(repo, "rev-parse", "HEAD", check=False)
    branch = git(repo, "branch", "--show-current", check=False)
    report["head"] = head.stdout.strip() if head.returncode == 0 else None
    report["branch"] = branch.stdout.strip() if branch.returncode == 0 else None

    base = git(repo, "rev-parse", "--verify", "origin/main", check=False)
    report["origin_main"] = base.stdout.strip() if base.returncode == 0 else None
    if base.returncode != 0:
        errors.append("origin/main does not exist; fetch it before continuing")

    changed = changed_paths(repo)
    report["changed_paths"] = changed
    if args.mode == "start" and changed:
        warnings.append("pre-existing changes detected; record and exclude these paths")

    scope: set[str] = set()
    if args.mode == "publish":
        if args.scope_file is None:
            errors.append("--scope-file is required in publish mode")
        elif not args.scope_file.is_file():
            errors.append(f"scope file not found: {args.scope_file}")
        else:
            scope, scope_errors = read_scope(args.scope_file)
            errors.extend(scope_errors)
        report["scope_paths"] = sorted(scope)
        out_of_scope = sorted(set(changed) - scope)
        unchanged_scope = sorted(scope - set(changed))
        report["out_of_scope_paths"] = out_of_scope
        report["unchanged_scope_paths"] = unchanged_scope
        if out_of_scope:
            errors.append("changed paths exist outside the declared stage scope")
        if unchanged_scope:
            warnings.append("scope lists paths that are not currently changed")

    inspected = scope if args.mode == "publish" else set(changed)
    unsafe = {path: reason for path in sorted(inspected) if (reason := unsafe_reason(path))}
    report["unsafe_paths"] = unsafe
    if unsafe:
        errors.append("unsafe paths require removal or explicit manual review")

    report["ok"] = not errors
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
