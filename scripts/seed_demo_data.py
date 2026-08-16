import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from campus_lost_found import Store
from campus_lost_found.demo_data import seed_demo_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed deterministic Campus Lost & Found demo data")
    parser.add_argument("--database", default=str(ROOT / "instance" / "campus_lost_found.db"))
    args = parser.parse_args()
    store = Store(args.database)
    seed_demo_data(store, reset=True)
    print(f"Demo data seeded: {store.database_path}")
    print("Accounts: minh.anh@campus.edu / Demo123!, gia.bao@campus.edu / Demo123!")


if __name__ == "__main__":
    main()
