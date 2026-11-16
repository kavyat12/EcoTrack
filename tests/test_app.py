import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app


class EcoTrackApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        app.db.DB_PATH = Path(cls.temp_directory.name) / "ecotrack.db"
        app.db.DATA_DIR = Path(cls.temp_directory.name)
        app.db.initialize_database()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.EcoTrackHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp_directory.cleanup()

    def setUp(self):
        with app.db.connect_database() as connection:
            connection.execute("DELETE FROM collections")
            connection.execute("DELETE FROM reports")
            connection.execute("DELETE FROM sessions")
            connection.execute("DELETE FROM users")
        self.cookie = None
        status, response = self.request(
            "/api/auth/register",
            "POST",
            {
                "display_name": "Eco Tester",
                "email": "eco@example.com",
                "password": "a secure passphrase",
            },
        )
        self.assertEqual(status, 201, response)

    def request(self, path, method="GET", payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        try:
            with urlopen(request, timeout=5) as response:
                body = response.read()
                if response.headers.get_content_type() == "application/json":
                    body = json.loads(body)
                cookie = response.headers.get("Set-Cookie")
                if cookie:
                    self.cookie = cookie.split(";", 1)[0]
                return response.status, body
        except HTTPError as error:
            with error:
                body = error.read()
                if error.headers.get_content_type() == "application/json":
                    body = json.loads(body)
                return error.code, body

    def test_registration_login_and_private_data(self):
        status, me = self.request("/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["display_name"], "Eco Tester")
        current_cookie = self.cookie
        self.cookie = None
        self.assertEqual(self.request("/api/dashboard")[0], 401)
        status, response = self.request(
            "/api/auth/login", "POST", {"email": "eco@example.com", "password": "incorrect"}
        )
        self.assertEqual(status, 401)
        self.cookie = None
        status, response = self.request(
            "/api/auth/login",
            "POST",
            {"email": "eco@example.com", "password": "a secure passphrase"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["user"]["email"], "eco@example.com")
        self.cookie = current_cookie
        status, response = self.request("/api/auth/register", "POST", {
            "display_name": "Duplicate", "email": "eco@example.com", "password": "another secure pass"
        })
        self.assertEqual(status, 409)

    def test_waste_carbon_recycling_and_analytics_flow(self):
        status, categories = self.request("/api/categories")
        self.assertEqual(status, 200)
        status, waste = self.request(
            "/api/waste",
            "POST",
            {
                "category_id": categories[0]["id"],
                "weight_kg": 4,
                "recycled_kg": 2.5,
                "note": "Washed bottles",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(waste["recycled_kg"], 2.5)

        status, carbon = self.request(
            "/api/carbon",
            "POST",
            {"activity_type": "car", "quantity": 10, "note": "Weekly errands"},
        )
        self.assertEqual(status, 201)
        self.assertAlmostEqual(carbon["emissions_kg"], 1.92)

        status, dashboard = self.request("/api/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["summary"]["waste_kg"], 4)
        self.assertEqual(dashboard["summary"]["recycled_kg"], 2.5)
        self.assertEqual(dashboard["summary"]["carbon_kg"], 1.92)
        self.assertIsNotNone(dashboard["summary"]["sustainability_score"])
        self.assertEqual(len(dashboard["monthly"]), 6)

        status, recycling = self.request("/api/recycling")
        self.assertEqual(status, 200)
        self.assertAlmostEqual(recycling["diversion_rate"], 62.5)
        self.assertTrue(recycling["guidance"])
        status, analytics = self.request("/api/analytics")
        self.assertEqual(status, 200)
        self.assertEqual(analytics["carbon_activities"][0]["activity_type"], "car")
        status, export = self.request("/api/analytics.csv")
        self.assertEqual(status, 200)
        self.assertIn(b"CO2e kg", export)

        self.assertEqual(self.request(f"/api/waste/{waste['id']}", "DELETE")[0], 200)
        self.assertEqual(self.request("/api/waste")[1], [])

    def test_entries_are_isolated_between_users(self):
        status, categories = self.request("/api/categories")
        self.assertEqual(status, 200)
        self.assertEqual(
            self.request(
                "/api/waste",
                "POST",
                {"category_id": categories[0]["id"], "weight_kg": 3, "recycled_kg": 1},
            )[0],
            201,
        )
        first_user_cookie = self.cookie
        status, _ = self.request(
            "/api/auth/register",
            "POST",
            {
                "display_name": "Second User",
                "email": "second@example.com",
                "password": "a different passphrase",
            },
        )
        self.assertEqual(status, 201)
        status, waste = self.request("/api/waste")
        self.assertEqual(status, 200)
        self.assertEqual(waste, [])
        self.cookie = first_user_cookie
        self.assertEqual(len(self.request("/api/waste")[1]), 1)

    def test_validation_profile_and_report_collection_workflow(self):
        status, categories = self.request("/api/categories")
        self.assertEqual(status, 200)
        status, error = self.request(
            "/api/waste",
            "POST",
            {"category_id": categories[0]["id"], "weight_kg": 1, "recycled_kg": 2},
        )
        self.assertEqual(status, 400)
        self.assertIn("between 0", error["error"])
        self.assertEqual(
            self.request(
                "/api/carbon", "POST", {"activity_type": "unknown", "quantity": 2}
            )[0],
            400,
        )

        status, report = self.request(
            "/api/reports",
            "POST",
            {
                "title": "Overflowing recycling bins",
                "category": categories[0]["id"],
                "location": "Oak Street park",
                "description": "Bins are full.",
                "urgency": "high",
            },
        )
        self.assertEqual(status, 201)
        status, collection = self.request(
            "/api/collections",
            "POST",
            {
                "area": "Oak Street park",
                "scheduled_date": "2026-12-01",
                "assigned_to": "Green Crew",
                "report_id": report["id"],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(self.request("/api/reports")[1][0]["status"], "scheduled")
        self.assertEqual(
            self.request(
                f"/api/collections/{collection['id']}", "PATCH", {"status": "completed"}
            )[0],
            200,
        )
        self.assertEqual(self.request("/api/reports")[1][0]["status"], "resolved")

        status, profile = self.request(
            "/api/profile",
            "PATCH",
            {"display_name": "New Name", "email": "new@example.com"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(profile["user"]["display_name"], "New Name")

    def test_auth_screen_and_dashboard_are_served(self):
        status, page = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"auth-screen", page)
        status, dashboard = self.request("/api/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("sustainability_score", dashboard["summary"])


if __name__ == "__main__":
    unittest.main()
