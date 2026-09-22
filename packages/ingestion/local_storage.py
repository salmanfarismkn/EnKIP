from pathlib import Path

from .storage import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve_key(key)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._resolve_key(key)

        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve_key(key)

        if path.exists():
            path.unlink()

    def _resolve_key(self, key: str) -> Path:
        path = (self._root / key).resolve()

        if self._root not in path.parents:
            raise ValueError("Storage key escapes storage root")

        return path