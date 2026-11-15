import argparse
import hashlib
import json
import os
import subprocess
import tarfile
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


def verify_manifest(archive_root: Path) -> dict:
    manifest_path = archive_root / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Backup manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for section in ("database_dump", "source_archive"):
        path = archive_root / manifest[section]["file"]
        if not path.is_file():
            raise SystemExit(f"Backup file is missing: {manifest[section]['file']}")
        if sha256(path) != manifest[section]["sha256"]:
            raise SystemExit(f"Backup checksum failed: {manifest[section]['file']}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--target-storage-root", required=True)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL for the isolated restore target must be configured")
    if os.environ.get("ENKIP_ALLOW_DESTRUCTIVE_RESTORE") != "true":
        raise SystemExit(
            "set ENKIP_ALLOW_DESTRUCTIVE_RESTORE=true only for an explicitly "
            "isolated restore target"
        )

    archive_root = Path(args.archive).resolve()
    manifest = verify_manifest(archive_root)
    connection = pg_connection(database_url)
    if not connection["database"] or not connection["user"]:
        raise SystemExit("DATABASE_URL must include user and database name")

    target = Path(args.target_storage_root).resolve()
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise SystemExit(
            "target storage must be empty; refusing to overwrite existing files"
        )

    env = os.environ.copy()
    if connection["password"]:
        env["PGPASSWORD"] = connection["password"]
    dump = archive_root / manifest["database_dump"]["file"]
    subprocess.run(
        [
            "pg_restore",
            "-h",
            connection["host"],
            "-p",
            connection["port"],
            "-U",
            connection["user"],
            "-d",
            connection["database"],
            "--clean",
            "--if-exists",
            "--no-owner",
            str(dump),
        ],
        check=True,
        env=env,
    )

    source_archive = archive_root / manifest["source_archive"]["file"]
    source_manifest = json.loads(
        (archive_root / manifest["source_manifest"]).read_text(encoding="utf-8")
    )
    with tarfile.open(source_archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise SystemExit("Source archive contains an unsafe path")
            if member.issym() or member.islnk():
                raise SystemExit("Source archive contains a link entry")
            if not member.isdir() and not member.isfile():
                raise SystemExit("Source archive contains an unsupported entry")

            destination = (target / member.name).resolve()
            if target not in destination.parents and destination != target:
                raise SystemExit("Source archive contains an unsafe path")

            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise SystemExit(f"Source archive entry could not be read: {member.name}")
            with destination.open("wb") as output:
                output.write(extracted.read())

    for relative, expected in source_manifest.items():
        path = target / relative
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"Restored source checksum failed: {relative}")
    print("Restore completed; database and source checksums verified")


if __name__ == "__main__":
    main()
