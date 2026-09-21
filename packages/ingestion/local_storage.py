from pathlib import Path

from .storage import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path) -> None:
        self._root = root

    def put(self, key: str, data: bytes) -> None:
        path = self._root / key

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._root / key

        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._root / key

        if path.exists():
            path.unlink()