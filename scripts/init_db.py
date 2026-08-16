import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from campus_lost_found import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the Campus Lost & Found SQLite database")
    parser.add_argument("--database", default=str(ROOT / "instance" / "campus_lost_found.db"))
    args = parser.parse_args()
    store = Store(args.database)
    store.init_db()
    print(f"Database initialized: {store.database_path}")


if __name__ == "__main__":
    main()

