import os
import sys
from pathlib import Path

# Each test run gets a fresh SQLite database and no production settings.
os.environ["DATABASE_URL"] = ""
os.environ.pop("JWT_SECRET", None)
db_file = Path(__file__).parent / "test.db"
if db_file.exists():
    db_file.unlink()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
