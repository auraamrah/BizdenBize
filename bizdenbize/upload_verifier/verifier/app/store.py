"""Hackathon-grade pHash store: a newline-separated hex file. Swap for Redis/PostgreSQL later."""
import pathlib
import imagehash

DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "known_hashes.txt"
_cache: list | None = None


def known_hashes() -> list[imagehash.ImageHash]:
    global _cache
    if _cache is None:
        _cache = [imagehash.hex_to_hash(l.strip()) for l in DB.read_text().splitlines()
                  if l.strip()] if DB.exists() else []
    return _cache


def add_hashes(hexes: list[str]) -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    with DB.open("a") as f:
        f.writelines(h + "\n" for h in hexes)
    known_hashes().extend(imagehash.hex_to_hash(h) for h in hexes)
