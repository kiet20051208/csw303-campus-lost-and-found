from __future__ import annotations

import hashlib
import hmac
import html
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http import HTTPStatus
from pathlib import Path
from string import Template
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urlencode


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "instance" / "campus_lost_found.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UNSAFE_RE = re.compile(r"<\s*/?\s*(script|iframe|object|embed|svg)|javascript:", re.IGNORECASE)


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then release the SQLite file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: Any, field: str, *, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise AppError(400, "INVALID_INPUT", f"{field} must be text")
    value = value.strip()
    if required and not value:
        raise AppError(400, "REQUIRED_FIELD", f"{field} is required")
    if len(value) > maximum:
        raise AppError(422, "INPUT_TOO_LONG", f"{field} must not exceed {maximum} characters")
    if UNSAFE_RE.search(value):
        raise AppError(422, "UNSAFE_INPUT", f"{field} contains disallowed markup")
    return value


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return salt.hex(), digest.hex()


class Store:
    def __init__(self, database_path: str | Path = DEFAULT_DB):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT NOT NULL CHECK(report_type IN ('LOST', 'FOUND')),
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            event_date TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Returned', 'Closed')),
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_active_search
            ON reports(status, report_type, category, location, event_date);
        """
        with self.connect() as connection:
            connection.executescript(schema)

    def clear_all(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                "DELETE FROM status_events; DELETE FROM contacts; DELETE FROM sessions; "
                "DELETE FROM reports; DELETE FROM users;"
            )

    def register(self, name: str, email: str, password: str, *, is_admin: bool = False) -> dict[str, Any]:
        name = normalize_text(name, "name", maximum=80)
        email = normalize_text(email, "email", maximum=160).lower()
        if not EMAIL_RE.match(email):
            raise AppError(400, "INVALID_EMAIL", "enter a valid email address")
        if not isinstance(password, str) or len(password) < 8:
            raise AppError(400, "WEAK_PASSWORD", "password must contain at least 8 characters")
        if len(password) > 128:
            raise AppError(422, "INPUT_TOO_LONG", "password must not exceed 128 characters")
        salt, digest = hash_password(password)
        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO users(name,email,password_salt,password_hash,is_admin,created_at) VALUES(?,?,?,?,?,?)",
                    (name, email, salt, digest, int(is_admin), utc_now()),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise AppError(409, "DUPLICATE_EMAIL", "an account with this email already exists") from error
        return {"id": user_id, "name": name, "email": email, "is_admin": bool(is_admin)}

    def authenticate(self, email: str, password: str) -> str:
        email = normalize_text(email, "email", maximum=160).lower()
        if not isinstance(password, str):
            raise AppError(400, "INVALID_INPUT", "password must be text")
        with self.connect() as connection:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if not user:
                raise AppError(401, "INVALID_CREDENTIALS", "invalid email or password")
            _, candidate = hash_password(password, bytes.fromhex(user["password_salt"]))
            if not hmac.compare_digest(candidate, user["password_hash"]):
                raise AppError(401, "INVALID_CREDENTIALS", "invalid email or password")
            token = secrets.token_urlsafe(32)
            connection.execute(
                "INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)",
                (token, user["id"], utc_now()),
            )
        return token

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def user_for_token(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT u.id,u.name,u.email,u.is_admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def require_user(self, token: str | None) -> dict[str, Any]:
        user = self.user_for_token(token)
        if not user:
            raise AppError(401, "AUTHENTICATION_REQUIRED", "authentication is required")
        return user

    def create_report(
        self,
        token: str | None,
        report_type: str,
        item_name: str,
        category: str,
        location: str,
        event_date: str,
        description: str,
    ) -> dict[str, Any]:
        user = self.require_user(token)
        report_type = normalize_text(report_type, "report type", maximum=10).upper()
        if report_type not in {"LOST", "FOUND"}:
            raise AppError(400, "INVALID_REPORT_TYPE", "report type must be LOST or FOUND")
        item_name = normalize_text(item_name, "item name", maximum=120)
        category = normalize_text(category, "category", maximum=60)
        location = normalize_text(location, "location", maximum=100)
        description = normalize_text(description, "description", maximum=1000)
        try:
            date.fromisoformat(event_date)
        except (TypeError, ValueError) as error:
            raise AppError(400, "INVALID_DATE", "event date must use YYYY-MM-DD") from error
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO reports(report_type,item_name,category,location,event_date,description,status,owner_id,created_at)
                   VALUES(?,?,?,?,?,?,'Active',?,?)""",
                (report_type, item_name, category, location, event_date, description, user["id"], utc_now()),
            )
            report_id = cursor.lastrowid
        return self.get_report(report_id)

    def get_report(self, report_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT r.*,u.name AS owner_name
                   FROM reports r JOIN users u ON u.id=r.owner_id WHERE r.id=?""",
                (report_id,),
            ).fetchone()
        if not row:
            raise AppError(404, "REPORT_NOT_FOUND", "report was not found")
        result = dict(row)
        result.pop("owner_id", None)
        return result

    def list_reports(
        self,
        *,
        keyword: str = "",
        category: str = "",
        location: str = "",
        start_date: str = "",
        end_date: str = "",
        status: str = "Active",
    ) -> list[dict[str, Any]]:
        keyword = normalize_text(keyword, "keyword", maximum=120, required=False)
        category = normalize_text(category, "category", maximum=60, required=False)
        location = normalize_text(location, "location", maximum=100, required=False)
        clauses = ["r.status = ?"]
        params: list[Any] = [status]
        if keyword:
            clauses.append("(r.item_name LIKE ? OR r.description LIKE ?)")
            pattern = f"%{keyword}%"
            params.extend([pattern, pattern])
        if category:
            clauses.append("r.category = ? COLLATE NOCASE")
            params.append(category)
        if location:
            clauses.append("r.location = ? COLLATE NOCASE")
            params.append(location)
        if start_date:
            try:
                date.fromisoformat(start_date)
            except ValueError as error:
                raise AppError(400, "INVALID_DATE", "start date must use YYYY-MM-DD") from error
            clauses.append("r.event_date >= ?")
            params.append(start_date)
        if end_date:
            try:
                date.fromisoformat(end_date)
            except ValueError as error:
                raise AppError(400, "INVALID_DATE", "end date must use YYYY-MM-DD") from error
            clauses.append("r.event_date <= ?")
            params.append(end_date)
        if start_date and end_date and start_date > end_date:
            raise AppError(400, "INVALID_DATE_RANGE", "start date must not be after end date")
        query = f"""SELECT r.*,u.name AS owner_name FROM reports r JOIN users u ON u.id=r.owner_id
                    WHERE {' AND '.join(clauses)} ORDER BY r.event_date DESC,r.id DESC"""
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def categories_and_locations(self) -> tuple[list[str], list[str]]:
        with self.connect() as connection:
            categories = [row[0] for row in connection.execute("SELECT DISTINCT category FROM reports ORDER BY category")]
            locations = [row[0] for row in connection.execute("SELECT DISTINCT location FROM reports ORDER BY location")]
        return categories, locations

    def contact(self, token: str | None, report_id: int, message: str) -> dict[str, Any]:
        user = self.require_user(token)
        message = normalize_text(message, "message", maximum=500)
        with self.connect() as connection:
            report = connection.execute("SELECT id,status FROM reports WHERE id=?", (report_id,)).fetchone()
            if not report:
                raise AppError(404, "REPORT_NOT_FOUND", "report was not found")
            if report["status"] != "Active":
                raise AppError(409, "REPORT_NOT_ACTIVE", "contact is only available for Active reports")
            cursor = connection.execute(
                "INSERT INTO contacts(report_id,sender_id,message,created_at) VALUES(?,?,?,?)",
                (report_id, user["id"], message, utc_now()),
            )
            return {"contactId": cursor.lastrowid, "reportId": report_id, "senderId": user["id"]}

    def mark_returned(self, token: str | None, report_id: int) -> dict[str, Any]:
        user = self.require_user(token)
        with self.connect() as connection:
            report = connection.execute("SELECT id,status,owner_id FROM reports WHERE id=?", (report_id,)).fetchone()
            if not report:
                raise AppError(404, "REPORT_NOT_FOUND", "report was not found")
            if user["id"] != report["owner_id"] and not user["is_admin"]:
                raise AppError(403, "NOT_AUTHORIZED", "only the report owner or administrator may mark it Returned")
            if report["status"] == "Returned":
                return {"reportId": report_id, "status": "Returned", "changed": False, "idempotent": True}
            if report["status"] != "Active":
                raise AppError(409, "INVALID_STATE_TRANSITION", f"cannot change {report['status']} to Returned")
            connection.execute("UPDATE reports SET status='Returned' WHERE id=?", (report_id,))
            connection.execute(
                "INSERT INTO status_events(report_id,from_status,to_status,actor_id,created_at) VALUES(?,?,?,?,?)",
                (report_id, "Active", "Returned", user["id"], utc_now()),
            )
        return {"reportId": report_id, "status": "Returned", "changed": True, "idempotent": False}

    def returned_history(self) -> list[dict[str, Any]]:
        return self.list_reports(status="Returned")

    def matches_for(self, report_id: int) -> list[dict[str, Any]]:
        source = self.get_report(report_id)
        opposite = "FOUND" if source["report_type"] == "LOST" else "LOST"
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.*,u.name AS owner_name,
                   (CASE WHEN r.category=? COLLATE NOCASE THEN 3 ELSE 0 END +
                    CASE WHEN r.location=? COLLATE NOCASE THEN 2 ELSE 0 END +
                    CASE WHEN r.event_date=? THEN 1 ELSE 0 END) AS score
                   FROM reports r JOIN users u ON u.id=r.owner_id
                   WHERE r.report_type=? AND r.status='Active' AND r.id<>?
                   ORDER BY score DESC,r.event_date DESC,r.id DESC""",
                (source["category"], source["location"], source["event_date"], opposite, report_id),
            ).fetchall()
        return [dict(row) for row in rows if row["score"] > 0]

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            values = {
                "active": connection.execute("SELECT COUNT(*) FROM reports WHERE status='Active'").fetchone()[0],
                "returned": connection.execute("SELECT COUNT(*) FROM reports WHERE status='Returned'").fetchone()[0],
                "users": connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            }
        return values


@dataclass
class Request:
    environ: dict[str, Any]

    @property
    def method(self) -> str:
        return self.environ.get("REQUEST_METHOD", "GET").upper()

    @property
    def path(self) -> str:
        return self.environ.get("PATH_INFO", "/") or "/"

    @property
    def query(self) -> dict[str, str]:
        return {key: values[-1] for key, values in parse_qs(self.environ.get("QUERY_STRING", ""), keep_blank_values=True).items()}

    def form(self) -> dict[str, str]:
        try:
            length = int(self.environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = self.environ["wsgi.input"].read(length).decode("utf-8") if length else ""
        return {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}

    @property
    def cookies(self) -> dict[str, str]:
        result = {}
        for part in self.environ.get("HTTP_COOKIE", "").split(";"):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                result[key] = value
        return result


class CampusLostFoundApp:
    def __init__(self, store: Store):
        self.store = store
        self.base_template = Template((ROOT / "templates" / "base.html").read_text(encoding="utf-8"))

    def __call__(self, environ: dict[str, Any], start_response):
        request = Request(environ)
        try:
            status, headers, body = self.dispatch(request)
        except AppError as error:
            status = error.status
            body = self.page(
                request,
                f"{error.code}",
                f'<section class="surface narrow"><p class="eyebrow error">Request could not be completed</p>'
                f"<h1>{html.escape(error.message)}</h1><p><a class=\"button secondary\" href=\"/\">Return home</a></p></section>",
            )
            headers = []
        except Exception:
            status = 500
            body = self.page(request, "Server error", '<section class="surface narrow"><h1>Something went wrong</h1><p>The request could not be completed safely.</p></section>')
            headers = []
        if not any(name.lower() == "content-type" for name, _ in headers):
            headers.insert(0, ("Content-Type", "text/html; charset=utf-8"))
        headers.append(("Content-Length", str(len(body.encode("utf-8")))))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [body.encode("utf-8")]

    def dispatch(self, request: Request) -> tuple[int, list[tuple[str, str]], str]:
        if request.path == "/static/style.css":
            css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
            return 200, [("Content-Type", "text/css; charset=utf-8")], css
        if request.path == "/" and request.method == "GET":
            return 200, [], self.home(request)
        if request.path == "/register":
            return self.register_route(request)
        if request.path == "/login":
            return self.login_route(request)
        if request.path == "/logout" and request.method == "POST":
            self.store.logout(request.cookies.get("session_token"))
            return self.redirect("/?message=Signed+out", clear_cookie=True)
        if request.path == "/reports" and request.method == "GET":
            return 200, [], self.report_list(request)
        if request.path == "/reports/new":
            return self.new_report_route(request)
        if request.path == "/history" and request.method == "GET":
            self.store.require_user(request.cookies.get("session_token"))
            return 200, [], self.history_page(request)
        match = re.fullmatch(r"/reports/(\d+)", request.path)
        if match and request.method == "GET":
            return 200, [], self.detail_page(request, int(match.group(1)))
        match = re.fullmatch(r"/reports/(\d+)/contact", request.path)
        if match and request.method == "POST":
            form = request.form()
            self.store.contact(request.cookies.get("session_token"), int(match.group(1)), form.get("message", ""))
            return self.redirect(f"/reports/{match.group(1)}?message=Contact+request+recorded")
        match = re.fullmatch(r"/reports/(\d+)/returned", request.path)
        if match and request.method == "POST":
            self.store.mark_returned(request.cookies.get("session_token"), int(match.group(1)))
            return self.redirect(f"/reports/{match.group(1)}?message=Report+marked+Returned")
        raise AppError(404, "PAGE_NOT_FOUND", "page was not found")

    def current_user(self, request: Request) -> dict[str, Any] | None:
        return self.store.user_for_token(request.cookies.get("session_token"))

    def page(self, request: Request, title: str, content: str) -> str:
        user = self.current_user(request)
        if user:
            account = f'<span class="account">{html.escape(user["name"])}</span><form action="/logout" method="post"><button class="nav-link" type="submit">Logout</button></form>'
            auth_links = f'<a href="/history">History</a>{account}'
        else:
            auth_links = '<a href="/login">Login</a><a class="nav-cta" href="/register">Register</a>'
        message = request.query.get("message", "")
        flash = f'<div class="flash">{html.escape(message)}</div>' if message else ""
        return self.base_template.safe_substitute(title=html.escape(title), auth_links=auth_links, flash=flash, content=content)

    def home(self, request: Request) -> str:
        counts = self.store.counts()
        content = f"""
        <section class="hero">
          <div><p class="eyebrow">Centralized campus recovery</p><h1>Lost something?<br>Let’s reconnect it.</h1>
          <p class="lede">Report, search and recover campus belongings through one privacy-aware workflow.</p>
          <div class="actions"><a class="button" href="/reports">Explore reports</a><a class="button secondary" href="/reports/new">Report an item</a></div></div>
          <aside class="hero-panel"><p class="eyebrow">Demo-ready baseline</p><div class="metric"><strong>{counts['active']}</strong><span>active reports</span></div>
          <div class="metric"><strong>{counts['returned']}</strong><span>returned cases</span></div><p>Search and combined filters read directly from SQLite.</p></aside>
        </section>
        <section class="feature-strip"><article><span>01</span><h2>Report clearly</h2><p>Structured Lost and Found reports keep category, location and date consistent.</p></article>
        <article><span>02</span><h2>Search precisely</h2><p>Combine keyword, category, location and inclusive date boundaries.</p></article>
        <article><span>03</span><h2>Recover safely</h2><p>Contact events protect private details and Returned status persists.</p></article></section>
        """
        return self.page(request, "Campus Lost & Found", content)

    def register_route(self, request: Request):
        if request.method == "POST":
            form = request.form()
            self.store.register(form.get("name", ""), form.get("email", ""), form.get("password", ""))
            return self.redirect("/login?message=Account+created")
        content = self.form_shell("Create a campus account", "Use a demo email, not personal credentials.", """
          <label>Name<input name="name" maxlength="80" required></label>
          <label>Email<input name="email" type="email" maxlength="160" required></label>
          <label>Password<input name="password" type="password" minlength="8" maxlength="128" required></label>
          <button class="button" type="submit">Create account</button>
        """)
        return 200, [], self.page(request, "Register", content)

    def login_route(self, request: Request):
        if request.method == "POST":
            form = request.form()
            token = self.store.authenticate(form.get("email", ""), form.get("password", ""))
            return self.redirect("/?message=Welcome+back", cookie=token)
        content = self.form_shell("Welcome back", "Sign in to report, contact or close a case.", """
          <label>Email<input name="email" type="email" required></label>
          <label>Password<input name="password" type="password" required></label>
          <button class="button" type="submit">Login</button>
        """)
        return 200, [], self.page(request, "Login", content)

    def new_report_route(self, request: Request):
        self.store.require_user(request.cookies.get("session_token"))
        if request.method == "POST":
            form = request.form()
            report = self.store.create_report(
                request.cookies.get("session_token"), form.get("report_type", ""), form.get("item_name", ""),
                form.get("category", ""), form.get("location", ""), form.get("event_date", ""), form.get("description", ""),
            )
            return self.redirect(f"/reports/{report['id']}?message=Report+created")
        options = "".join(f'<option>{html.escape(value)}</option>' for value in ["Electronics", "Identification", "Bag", "Books", "Clothing", "Bottle", "Other"])
        fields = f"""
          <fieldset class="type-switch"><legend>Report type</legend><label><input type="radio" name="report_type" value="LOST" checked> Lost</label><label><input type="radio" name="report_type" value="FOUND"> Found</label></fieldset>
          <label>Item name<input name="item_name" maxlength="120" required></label>
          <label>Category<select name="category" required><option value="">Select category</option>{options}</select></label>
          <label>Location<input name="location" maxlength="100" placeholder="e.g. Main Library" required></label>
          <label>Date<input name="event_date" type="date" required></label>
          <label class="full">Description<textarea name="description" maxlength="1000" required placeholder="Use recognizable details, but do not publish IDs, phone numbers or proof-of-ownership data."></textarea></label>
          <button class="button" type="submit">Publish report</button>
        """
        return 200, [], self.page(request, "New report", self.form_shell("Create a Lost / Found report", "Required fields are validated and saved to SQLite.", fields, wide=True))

    def report_list(self, request: Request) -> str:
        query = request.query
        reports = self.store.list_reports(
            keyword=query.get("keyword", ""), category=query.get("category", ""), location=query.get("location", ""),
            start_date=query.get("start_date", ""), end_date=query.get("end_date", ""),
        )
        categories, locations = self.store.categories_and_locations()
        category_options = self.options(categories, query.get("category", ""), "All categories")
        location_options = self.options(locations, query.get("location", ""), "All locations")
        filters = f"""
        <form class="filters" method="get"><label>Keyword<input name="keyword" value="{html.escape(query.get('keyword',''))}" placeholder="wallet, headphones..."></label>
        <label>Category<select name="category">{category_options}</select></label><label>Location<select name="location">{location_options}</select></label>
        <label>Start date<input type="date" name="start_date" value="{html.escape(query.get('start_date',''))}"></label>
        <label>End date<input type="date" name="end_date" value="{html.escape(query.get('end_date',''))}"></label>
        <button class="button" type="submit">Apply filters</button><a class="button secondary" href="/reports">Clear</a></form>
        """
        cards = "".join(self.report_card(report) for report in reports)
        if not cards:
            cards = '<div class="empty"><h2>No matching reports</h2><p>Clear or adjust the filters and try again.</p></div>'
        content = f'<section class="page-heading"><p class="eyebrow">US-06 • live database query</p><h1>Active Lost & Found reports</h1><p>Combine category, location and inclusive date filters.</p></section>{filters}<section class="report-grid">{cards}</section>'
        return self.page(request, "Reports", content)

    def detail_page(self, request: Request, report_id: int) -> str:
        report = self.store.get_report(report_id)
        user = self.current_user(request)
        can_return = bool(user and (user["id"] == self.owner_id(report_id) or user["is_admin"]))
        contact = ""
        returned = ""
        if report["status"] == "Active":
            if user:
                contact = f"""<section class="surface"><h2>Safe contact</h2><div class="privacy"><strong>Privacy notice:</strong> Your request is recorded. Personal email and phone details are not displayed publicly.</div>
                <form action="/reports/{report_id}/contact" method="post"><label>Message<textarea name="message" maxlength="500" required placeholder="Describe why this may be a match"></textarea></label><button class="button" type="submit">Send contact request</button></form></section>"""
            else:
                contact = '<section class="surface"><h2>Safe contact</h2><p><a href="/login">Login</a> to start a privacy-safe contact request.</p></section>'
            if can_return:
                returned = f'<section class="surface"><h2>Resolve this case</h2><p>Only the report owner or administrator can update this status.</p><form action="/reports/{report_id}/returned" method="post"><button class="button" type="submit">Mark as Returned</button></form></section>'
        matches = self.store.matches_for(report_id) if report["status"] == "Active" else []
        matches_html = "".join(self.report_card(item, compact=True) for item in matches[:3]) or '<p class="muted">No active suggestions currently meet the simple category/location/date score.</p>'
        content = f"""<p><a href="/reports">← Back to reports</a></p><section class="detail surface"><div><span class="badge {report['report_type'].lower()}">{report['report_type']}</span><span class="status {report['status'].lower()}">{html.escape(report['status'])}</span></div>
        <h1>{html.escape(report['item_name'])}</h1><p class="lede small">{html.escape(report['description'])}</p><dl><div><dt>Category</dt><dd>{html.escape(report['category'])}</dd></div><div><dt>Location</dt><dd>{html.escape(report['location'])}</dd></div><div><dt>Date</dt><dd>{html.escape(report['event_date'])}</dd></div><div><dt>Reported by</dt><dd>{html.escape(report['owner_name'])}</dd></div></dl></section>
        <div class="two-column">{contact}{returned}</div><section class="related"><p class="eyebrow">Possible active matches</p><div class="report-grid compact">{matches_html}</div></section>"""
        return self.page(request, report["item_name"], content)

    def history_page(self, request: Request) -> str:
        cards = "".join(self.report_card(report) for report in self.store.returned_history()) or '<div class="empty"><h2>No returned cases yet</h2></div>'
        return self.page(request, "Returned history", f'<section class="page-heading"><p class="eyebrow">NFR-06 • persistent lifecycle</p><h1>Returned history</h1><p>Resolved reports leave active matching but remain traceable.</p></section><section class="report-grid">{cards}</section>')

    def owner_id(self, report_id: int) -> int:
        with self.store.connect() as connection:
            row = connection.execute("SELECT owner_id FROM reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            raise AppError(404, "REPORT_NOT_FOUND", "report was not found")
        return row[0]

    def report_card(self, report: dict[str, Any], compact: bool = False) -> str:
        return f"""<article class="report-card {'compact-card' if compact else ''}"><div><span class="badge {report['report_type'].lower()}">{report['report_type']}</span><span class="status {report['status'].lower()}">{html.escape(report['status'])}</span></div>
        <h2>{html.escape(report['item_name'])}</h2><p>{html.escape(report['description'])}</p><ul class="meta"><li>{html.escape(report['category'])}</li><li>{html.escape(report['location'])}</li><li>{html.escape(report['event_date'])}</li></ul><a class="text-link" href="/reports/{report['id']}">View details →</a></article>"""

    @staticmethod
    def form_shell(title: str, intro: str, fields: str, *, wide: bool = False) -> str:
        return f'<section class="surface form-page {"wide" if wide else ""}"><p class="eyebrow">Campus Lost & Found</p><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p><form method="post" class="form-grid">{fields}</form></section>'

    @staticmethod
    def options(values: Iterable[str], selected: str, empty_label: str) -> str:
        result = [f'<option value="">{html.escape(empty_label)}</option>']
        for value in values:
            marker = " selected" if value.lower() == selected.lower() else ""
            result.append(f'<option{marker}>{html.escape(value)}</option>')
        return "".join(result)

    @staticmethod
    def redirect(location: str, *, cookie: str | None = None, clear_cookie: bool = False):
        headers = [("Location", location)]
        if cookie:
            headers.append(("Set-Cookie", f"session_token={cookie}; Path=/; HttpOnly; SameSite=Lax"))
        if clear_cookie:
            headers.append(("Set-Cookie", "session_token=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"))
        return 303, headers, ""


def create_app(database_path: str | Path | None = None) -> CampusLostFoundApp:
    store = Store(database_path or os.environ.get("CAMPUS_LF_DB", DEFAULT_DB))
    store.init_db()
    return CampusLostFoundApp(store)
