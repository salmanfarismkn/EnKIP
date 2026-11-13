import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pg_connection(database_url: str) -> dict[str, str]:
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "database": unquote(parsed.path.lstrip("/")),
        "password": unquote(parsed.password or ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    source_root = os.environ.get("STORAGE_ROOT")
    if not database_url or not source_root:
        raise SystemExit("DATABASE_URL and STORAGE_ROOT must be configured")

    source = Path(source_root).resolve()
    if not source.is_dir():
        raise SystemExit("STORAGE_ROOT is not a readable directory")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive_root = output / f"enkip-backup-{timestamp}"
    archive_root.mkdir()

    connection = pg_connection(database_url)
    if not connection["database"] or not connection["user"]:
        raise SystemExit("DATABASE_URL must include user and database name")

    database_dump = archive_root / "database.dump"
    env = os.environ.copy()
    if connection["password"]:
        env["PGPASSWORD"] = connection["password"]
    subprocess.run(
        [
            "pg_dump",
            "-h",
            connection["host"],
            "-p",
            connection["port"],
            "-U",
            connection["user"],
            "-d",
            connection["database"],
            "-Fc",
            "-f",
            str(database_dump),
        ],
        check=True,
        env=env,
    )

    source_manifest = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            source_manifest[relative] = sha256(path)
    (archive_root / "source-manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    source_archive = archive_root / "source-storage.tar.gz"
    with tarfile.open(source_archive, "w:gz") as tar:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(source).as_posix())

    manifest = {
        "created_at": timestamp,
        "database_dump": {
            "file": database_dump.name,
            "sha256": sha256(database_dump),
        },
        "source_archive": {
            "file": source_archive.name,
            "sha256": sha256(source_archive),
        },
        "source_file_count": len(source_manifest),
        "source_manifest": "source-manifest.json",
    }
    (archive_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(str(archive_root))


if __name__ == "__main__":
    main()
