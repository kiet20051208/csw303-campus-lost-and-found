import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from campus_lost_found import Store


ACCOUNTS = (
    ("Nguyen Minh Anh", "minh.anh@campus.edu", "Demo123!", False),
    ("Tran Gia Bao", "gia.bao@campus.edu", "Demo123!", False),
    ("System Administrator", "admin@campus.edu", "Admin123!", True),
)


def seed(store: Store) -> None:
    store.init_db()
    store.clear_all()
    tokens = {}
    for name, email, password, is_admin in ACCOUNTS:
        store.register(name, email, password, is_admin=is_admin)
        tokens[email] = store.authenticate(email, password)

    today = date.today()
    reports = (
        ("minh.anh@campus.edu", "LOST", "Black wireless headphones", "Electronics", "Main Library", -2, "Black over-ear headphones in a gray fabric case."),
        ("gia.bao@campus.edu", "FOUND", "Wireless headphones", "Electronics", "Main Library", -1, "Found near the second-floor study desks; identifying details withheld."),
        ("minh.anh@campus.edu", "LOST", "Blue canvas backpack", "Bag", "Building A", -5, "Blue backpack with course notebooks inside."),
        ("gia.bao@campus.edu", "FOUND", "Silver smartphone", "Electronics", "Student Cafeteria", -3, "Phone found under a table; lock-screen details are not published."),
        ("minh.anh@campus.edu", "LOST", "Software Engineering notebook", "Books", "Building B", -7, "A5 ruled notebook with handwritten class notes."),
        ("gia.bao@campus.edu", "FOUND", "Green water bottle", "Bottle", "Sports Hall", -4, "Reusable green bottle found beside the east entrance."),
        ("minh.anh@campus.edu", "LOST", "Student ID card holder", "Identification", "Main Library", -8, "Dark card holder; private card number is intentionally omitted."),
        ("gia.bao@campus.edu", "FOUND", "Beige jacket", "Clothing", "Building A", -6, "Light jacket left in lecture room A203."),
    )
    for email, report_type, item, category, location, offset, description in reports:
        store.create_report(tokens[email], report_type, item, category, location, (today + timedelta(days=offset)).isoformat(), description)
    for token in tokens.values():
        store.logout(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed deterministic Campus Lost & Found demo data")
    parser.add_argument("--database", default=str(ROOT / "instance" / "campus_lost_found.db"))
    args = parser.parse_args()
    store = Store(args.database)
    seed(store)
    print(f"Demo data seeded: {store.database_path}")
    print("Accounts: minh.anh@campus.edu / Demo123!, gia.bao@campus.edu / Demo123!")


if __name__ == "__main__":
    main()

