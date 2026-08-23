#!/usr/bin/env python3
"""Restore GitHub-size-excluded perf_trace files and verify the source tree."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tarfile
import tempfile


ARCHIVES = {
    "acceptance/workflow01-10-fresh-e2e-dcu1-20260806-full-resolution.tar.gz": {
        "sha256": "75efc593c68b336af94b8a4ededd619e5d9088eaff19cf9089f1400f94e55b5c",
        "members": [
            "E2E_PROCESS_TIMELINE_LOSSLESS.html",
            "E2E_PROCESS_TIMELINE.full.perfetto.json",
        ],
    },
    "acceptance/workflow01-10-fresh-e2e-dcu1-20260806-full-resolution-v2.tar.gz": {
        "sha256": "7888a2d42d715f4e7d77070ec4a7ba07d314739d15543bcb9eaef35b5fa510fb",
        "members": [
            "E2E_PROCESS_TIMELINE_LOSSLESS.html",
            "E2E_PROCESS_TIMELINE.full.perfetto.json",
        ],
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def restore(root: Path) -> None:
    for archive_rel, specification in ARCHIVES.items():
        archive = root / archive_rel
        observed = sha256_file(archive)
        if observed != specification["sha256"]:
            raise RuntimeError(f"archive hash mismatch: {archive_rel}")
        directory_name = archive.name.removesuffix(".tar.gz")
        with tarfile.open(archive, "r:gz") as bundle:
            for filename in specification["members"]:
                member_name = f"{directory_name}/{filename}"
                member = bundle.getmember(member_name)
                source = bundle.extractfile(member)
                if source is None or not member.isfile():
                    raise RuntimeError(f"archive member is not a file: {member_name}")
                target = root / "acceptance" / directory_name / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
                    temporary = Path(tmp.name)
                    while block := source.read(1024 * 1024):
                        tmp.write(block)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.chmod(temporary, 0o644)
                os.replace(temporary, target)


def expected_hashes(root: Path) -> list[tuple[str, Path]]:
    result = []
    checksum_file = root / "SOURCE_TREE_SHA256SUMS"
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        relative = relative.removeprefix("./")
        result.append((digest, root / relative))
    return result


def verify(root: Path) -> None:
    failures = []
    for expected, path in expected_hashes(root):
        if not path.is_file():
            failures.append(f"missing: {path.relative_to(root)}")
            continue
        observed = sha256_file(path)
        if observed != expected:
            failures.append(f"hash mismatch: {path.relative_to(root)}")
    if failures:
        raise RuntimeError("source-tree verification failed:\n" + "\n".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="perf_trace checkout to restore (default: script directory)",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not args.verify_only:
        restore(root)
    verify(root)
    print(f"verified complete perf_trace source tree: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
