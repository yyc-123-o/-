from hashlib import sha256
from pathlib import Path

from .models import FileInventoryEntry


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def inventory_tree(root: Path) -> list[FileInventoryEntry]:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise ValueError(f"input root is not a directory: {resolved}")
    files = sorted(
        (path for path in resolved.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(resolved).as_posix(),
    )
    return [
        FileInventoryEntry(
            root=str(resolved),
            relative_path=path.relative_to(resolved).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in files
    ]
