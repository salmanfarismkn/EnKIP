import os
import tempfile
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

        if path.exists():
            raise FileExistsError(key)

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_path = Path(file.name)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())

            try:
                os.link(temp_path, path)
            except FileExistsError:
                raise FileExistsError(key)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def get(self, key: str) -> bytes:
        path = self._resolve_key(key)

        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve_key(key)

        if path.exists():
            path.unlink()

    def size(self, key: str) -> int:
        return self._resolve_key(key).stat().st_size

    def _resolve_key(self, key: str) -> Path:
        path = (self._root / key).resolve()

        if self._root not in path.parents:
            raise ValueError("Storage key escapes storage root")

        return path