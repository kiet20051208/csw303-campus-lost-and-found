from datetime import date, timedelta

from .app import Store


ACCOUNTS = (
    ("Nguyen Minh Anh", "minh.anh@campus.edu", "Demo123!", False),
    ("Tran Gia Bao", "gia.bao@campus.edu", "Demo123!", False),
    ("System Administrator", "admin@campus.edu", "Admin123!", True),
)


def seed_demo_data(store: Store, *, reset: bool = False) -> bool:
    """Seed a blank database once, or deliberately reset it for local demos."""
    store.init_db()
    if reset:
        store.clear_all()
    elif store.counts()["users"] > 0:
        return False

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
        store.create_report(
            tokens[email], report_type, item, category, location,
            (today + timedelta(days=offset)).isoformat(), description,
        )
    for token in tokens.values():
        store.logout(token)
    return True

