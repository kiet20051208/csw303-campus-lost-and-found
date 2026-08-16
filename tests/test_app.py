import io
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from campus_lost_found import Store, create_app
from campus_lost_found.app import AppError
from campus_lost_found.demo_data import seed_demo_data


class CampusLostFoundTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test.db"
        self.store = Store(self.database)
        self.store.init_db()
        self.alice = self.store.register("Alice Student", "alice@example.edu", "Password1!")
        self.bob = self.store.register("Bob Staff", "bob@example.edu", "Password2!")
        self.alice_token = self.store.authenticate("alice@example.edu", "Password1!")
        self.bob_token = self.store.authenticate("bob@example.edu", "Password2!")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_report(self, *, token=None, report_type="LOST", item="Black headphones", category="Electronics", location="Library", event_date="2026-08-12", description="Headphones in a gray case"):
        return self.store.create_report(token or self.alice_token, report_type, item, category, location, event_date, description)

    def assert_error(self, code, callback):
        with self.assertRaises(AppError) as context:
            callback()
        self.assertEqual(code, context.exception.code)


class AuthenticationTests(CampusLostFoundTestCase):
    def test_auth_01_register_hashes_password(self):
        with self.store.connect() as connection:
            row = connection.execute("SELECT password_hash FROM users WHERE id=?", (self.alice["id"],)).fetchone()
        self.assertNotEqual("Password1!", row[0])

    def test_auth_02_duplicate_registration_rejected(self):
        self.assert_error("DUPLICATE_EMAIL", lambda: self.store.register("Other", "ALICE@example.edu", "Password3!"))

    def test_auth_03_login_creates_valid_session(self):
        token = self.store.authenticate("alice@example.edu", "Password1!")
        self.assertEqual(self.alice["id"], self.store.user_for_token(token)["id"])

    def test_auth_04_invalid_login_rejected(self):
        self.assert_error("INVALID_CREDENTIALS", lambda: self.store.authenticate("alice@example.edu", "wrong-pass"))

    def test_auth_05_logout_invalidates_session(self):
        self.store.logout(self.alice_token)
        self.assertIsNone(self.store.user_for_token(self.alice_token))

    def test_auth_06_protected_report_creation_rejected(self):
        self.assert_error("AUTHENTICATION_REQUIRED", lambda: self.create_report(token="missing"))


class ReportTests(CampusLostFoundTestCase):
    def test_rep_01_create_lost_report(self):
        self.assertEqual("LOST", self.create_report()["report_type"])

    def test_rep_02_create_found_report(self):
        report = self.create_report(report_type="FOUND", item="Found phone")
        self.assertEqual("FOUND", report["report_type"])

    def test_rep_03_details_do_not_expose_private_identity(self):
        report = self.create_report()
        details = self.store.get_report(report["id"])
        self.assertNotIn("email", details)
        self.assertNotIn("owner_id", details)

    def test_rep_04_required_field_validation(self):
        self.assert_error("REQUIRED_FIELD", lambda: self.create_report(item=""))


class SearchAndFilterTests(CampusLostFoundTestCase):
    def setUp(self):
        super().setUp()
        self.create_report(item="Black headphones", category="Electronics", location="Library", event_date="2026-08-10")
        self.create_report(report_type="FOUND", item="Blue backpack", category="Bag", location="Building A", event_date="2026-08-12", description="Backpack beside room A203")
        self.create_report(report_type="FOUND", item="Silver phone", category="Electronics", location="Cafeteria", event_date="2026-08-15", description="Phone found beneath a table")

    def test_search_01_keyword_reads_database(self):
        self.assertEqual(["Black headphones"], [r["item_name"] for r in self.store.list_reports(keyword="headphones")])

    def test_search_02_filter_by_category(self):
        self.assertEqual(2, len(self.store.list_reports(category="Electronics")))

    def test_at_us06_01_combined_filters_satisfy_all_criteria(self):
        results = self.store.list_reports(category="Electronics", location="Library", start_date="2026-08-09", end_date="2026-08-11")
        self.assertEqual(["Black headphones"], [r["item_name"] for r in results])

    def test_at_us06_02_filter_by_location_and_inclusive_date(self):
        results = self.store.list_reports(location="Building A", start_date="2026-08-12", end_date="2026-08-12")
        self.assertEqual(["Blue backpack"], [r["item_name"] for r in results])

    def test_at_us06_03_clear_no_results_state(self):
        self.assertEqual([], self.store.list_reports(category="Bag", location="Cafeteria"))

    def test_search_05_invalid_date_range_is_controlled(self):
        self.assert_error("INVALID_DATE_RANGE", lambda: self.store.list_reports(start_date="2026-08-20", end_date="2026-08-10"))


class ContactTests(CampusLostFoundTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.create_report()

    def test_at_us09_01_safe_contact_flow_is_available(self):
        self.assertEqual("Active", self.store.get_report(self.report["id"])["status"])
        result = self.store.contact(self.bob_token, self.report["id"], "I may have found this item.")
        self.assertGreater(result["contactId"], 0)

    def test_at_us09_02_contact_event_is_recorded(self):
        result = self.store.contact(self.bob_token, self.report["id"], "I may have found this item.")
        with self.store.connect() as connection:
            event = connection.execute("SELECT report_id,sender_id FROM contacts WHERE id=?", (result["contactId"],)).fetchone()
        self.assertEqual((self.report["id"], self.bob["id"]), tuple(event))

    def test_at_us09_03_privacy_warning_contract_hides_email(self):
        self.assertNotIn("email", self.store.get_report(self.report["id"]))

    def test_contact_04_inactive_report_rejected(self):
        self.store.mark_returned(self.alice_token, self.report["id"])
        self.assert_error("REPORT_NOT_ACTIVE", lambda: self.store.contact(self.bob_token, self.report["id"], "Message"))


class ReturnedLifecycleTests(CampusLostFoundTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.create_report()

    def test_at_us12_01_owner_can_mark_returned(self):
        result = self.store.mark_returned(self.alice_token, self.report["id"])
        self.assertTrue(result["changed"])
        self.assertEqual("Returned", result["status"])

    def test_at_us12_02_returned_case_is_excluded_from_active_matching(self):
        found = self.create_report(token=self.bob_token, report_type="FOUND", item="Found headphones")
        self.assertIn(self.report["id"], [r["id"] for r in self.store.matches_for(found["id"])])
        self.store.mark_returned(self.alice_token, self.report["id"])
        self.assertNotIn(self.report["id"], [r["id"] for r in self.store.matches_for(found["id"])])

    def test_at_us12_03_returned_report_leaves_active_list_and_enters_history(self):
        self.store.mark_returned(self.alice_token, self.report["id"])
        self.assertNotIn(self.report["id"], [r["id"] for r in self.store.list_reports()])
        self.assertIn(self.report["id"], [r["id"] for r in self.store.returned_history()])

    def test_returned_04_unauthorized_user_is_rejected(self):
        self.assert_error("NOT_AUTHORIZED", lambda: self.store.mark_returned(self.bob_token, self.report["id"]))

    def test_rel_01_returned_status_persists_after_new_connection(self):
        self.store.mark_returned(self.alice_token, self.report["id"])
        reopened = Store(self.database)
        self.assertEqual("Returned", reopened.get_report(self.report["id"])["status"])

    def test_rel_02_invalid_transition_rejected(self):
        with self.store.connect() as connection:
            connection.execute("UPDATE reports SET status='Closed' WHERE id=?", (self.report["id"],))
        self.assert_error("INVALID_STATE_TRANSITION", lambda: self.store.mark_returned(self.alice_token, self.report["id"]))

    def test_rel_03_repeated_action_is_idempotent(self):
        self.store.mark_returned(self.alice_token, self.report["id"])
        result = self.store.mark_returned(self.alice_token, self.report["id"])
        with self.store.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM status_events WHERE report_id=?", (self.report["id"],)).fetchone()[0]
        self.assertTrue(result["idempotent"])
        self.assertEqual(1, count)

    def test_rel_04_failed_authorization_does_not_mutate_state(self):
        self.assert_error("NOT_AUTHORIZED", lambda: self.store.mark_returned(self.bob_token, self.report["id"]))
        self.assertEqual("Active", self.store.get_report(self.report["id"])["status"])


class SecurityTests(CampusLostFoundTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.create_report()

    def test_sec_01_unauthenticated_contact_rejected(self):
        self.assert_error("AUTHENTICATION_REQUIRED", lambda: self.store.contact(None, self.report["id"], "Message"))

    def test_sec_02_unauthenticated_returned_update_rejected(self):
        self.assert_error("AUTHENTICATION_REQUIRED", lambda: self.store.mark_returned(None, self.report["id"]))

    def test_sec_03_invalid_input_is_controlled(self):
        self.assert_error("INVALID_DATE", lambda: self.create_report(event_date="not-a-date"))

    def test_sec_04_empty_required_input_rejected(self):
        self.assert_error("REQUIRED_FIELD", lambda: self.store.contact(self.bob_token, self.report["id"], ""))

    def test_sec_05_overlong_input_rejected(self):
        self.assert_error("INPUT_TOO_LONG", lambda: self.store.contact(self.bob_token, self.report["id"], "x" * 501))

    def test_sec_06_script_like_input_rejected(self):
        self.assert_error("UNSAFE_INPUT", lambda: self.store.contact(self.bob_token, self.report["id"], "<script>alert(1)</script>"))


class WsgiIntegrationTests(CampusLostFoundTestCase):
    def request(self, path="/", method="GET", data=None, token=None):
        encoded = urlencode(data or {}).encode()
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path.split("?", 1)[0],
            "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
            "CONTENT_LENGTH": str(len(encoded)),
            "wsgi.input": io.BytesIO(encoded),
            "HTTP_COOKIE": f"session_token={token}" if token else "",
        }
        response = {}
        def start_response(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)
        body = b"".join(create_app(self.database)(environ, start_response)).decode()
        return int(response["status"].split()[0]), response["headers"], body

    def test_http_01_home_and_css_load(self):
        self.assertEqual(200, self.request("/")[0])
        status, headers, _ = self.request("/static/style.css")
        self.assertEqual(200, status)
        self.assertEqual("text/css; charset=utf-8", headers["Content-Type"])

    def test_http_02_protected_page_returns_controlled_401(self):
        status, _, body = self.request("/reports/new")
        self.assertEqual(401, status)
        self.assertIn("authentication is required", body)

    def test_http_03_direct_unauthorized_returned_request_is_blocked(self):
        report = self.create_report()
        status, _, _ = self.request(f"/reports/{report['id']}/returned", "POST", token=self.bob_token)
        self.assertEqual(403, status)
        self.assertEqual("Active", self.store.get_report(report["id"])["status"])

    def test_http_04_report_list_renders_empty_state(self):
        status, _, body = self.request("/reports?keyword=definitely-missing")
        self.assertEqual(200, status)
        self.assertIn("No matching reports", body)


class DeploymentStartupTests(unittest.TestCase):
    def test_deploy_01_blank_database_is_initialized_and_seeded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Store(Path(temp_dir) / "deploy.db")
            self.assertTrue(seed_demo_data(store))
            self.assertEqual(3, store.counts()["users"])
            self.assertEqual(8, store.counts()["active"])

    def test_deploy_02_existing_database_is_not_reset_or_duplicated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Store(Path(temp_dir) / "deploy.db")
            seed_demo_data(store)
            token = store.authenticate("minh.anh@campus.edu", "Demo123!")
            report = store.create_report(token, "LOST", "Persistent demo item", "Other", "Building C", "2026-08-16", "Must survive a second startup.")
            self.assertFalse(seed_demo_data(store))
            self.assertEqual("Persistent demo item", store.get_report(report["id"])["item_name"])
            self.assertEqual(9, store.counts()["active"])


if __name__ == "__main__":
    unittest.main()
