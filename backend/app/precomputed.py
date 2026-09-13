"""Small build-time summaries, invalidated when their data or calculation changes."""
import hashlib
from pathlib import Path


def signature(database: Path) -> str:
    digest = hashlib.sha256()
    for path in (database, Path(__file__), Path(__file__).with_name('analytics_sql.py'), Path(__file__).with_name('services.py')):
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
    return digest.hexdigest()
