import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import sqlite3
import time
from datetime import date, datetime, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import db
from impact import (
    ACTIVITY_TYPES,
    MATERIAL_GUIDANCE,
    month_keys,
    recommendations,
    sustainability_score,
)
from security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    new_session_token,
    session_token_digest,
    verify_password,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SESSION_COOKIE = "ecotrack_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14
MAX_REQUEST_SIZE = 64 * 1024
REPORT_STATUSES = {"open", "scheduled", "resolved"}
COLLECTION_STATUSES = {"scheduled", "in_progress", "completed"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DUMMY_PASSWORD_SALT = "00000000000000000000000000000000"
DUMMY_PASSWORD_HASH = hashlib.pbkdf2_hmac(
    "sha256", b"EcoTrack invalid account", bytes.fromhex(DUMMY_PASSWORD_SALT), 310_000
).hex()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("ecotrack")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def bounded_number(data, key, label, maximum):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise ValueError(f"{label} must be greater than 0 and no more than {maximum:g}.")
    return float(value)


class EcoTrackHandler(BaseHTTPRequestHandler):
    server_version = "EcoTrack/1.1"

    def log_message(self, message, *args):
        LOGGER.info("%s - %s", self.address_string(), message % args)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_cookie(self, token):
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_AGE}",
        )

    def send_cleared_cookie(self):
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request size.") from error
        if length <= 0 or length > MAX_REQUEST_SIZE:
            raise ValueError("Request body must be between 1 byte and 64 KB.")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request body must contain valid JSON.") from error
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    @staticmethod
    def required_text(data, key, label, maximum):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required.")
        value = value.strip()
        if len(value) > maximum:
            raise ValueError(f"{label} must be {maximum} characters or fewer.")
        return value

    def check_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlparse(origin)
        host = self.headers.get("Host", "")
        return parsed.scheme in {"http", "https"} and parsed.netloc == host

    def authenticate(self):
        self.current_user = None
        self.session_hash = None
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie[SESSION_COOKIE].value
        except (CookieError, KeyError, ValueError):
            return
        token_hash = session_token_digest(token)
        with db.connect_database() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.email, u.display_name, s.expires_at
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return
            if row["expires_at"] <= int(time.time()):
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                return
        self.current_user = {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
        }
        self.session_hash = token_hash

    def require_user(self):
        if self.current_user is not None:
            return True
        self.send_json(401, {"error": "Please sign in to continue.", "code": "unauthorized"})
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self.send_json(200, {"status": "ok"})
                return
            self.authenticate()
            if path == "/api/auth/me":
                if self.current_user is None:
                    self.send_json(200, {"user": None})
                else:
                    self.send_json(200, {"user": self.current_user})
                return
            if not path.startswith("/api/"):
                self.serve_static(path)
                return
            if not self.require_user():
                return
            user_id = self.current_user["id"]
            if path == "/api/categories":
                self.get_categories(user_id)
            elif path == "/api/reports":
                self.get_reports(user_id)
            elif path == "/api/collections":
                self.get_collections(user_id)
            elif path == "/api/dashboard":
                self.get_dashboard(user_id)
            elif path == "/api/waste":
                self.get_waste(user_id)
            elif path == "/api/carbon":
                self.get_carbon(user_id)
            elif path == "/api/recycling":
                self.get_recycling(user_id)
            elif path == "/api/analytics":
                self.get_analytics(user_id)
            elif path == "/api/analytics.csv":
                self.get_analytics_csv(user_id)
            else:
                self.send_json(404, {"error": "Endpoint not found."})
        except sqlite3.Error:
            LOGGER.exception("Database error while handling GET %s", path)
            self.send_json(500, {"error": "The database could not complete this request."})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if not self.check_origin():
                self.send_json(403, {"error": "Cross-origin request rejected."})
                return
            if path == "/api/auth/logout":
                self.logout()
                return
            if path == "/api/auth/register":
                self.register(self.read_json())
                return
            if path == "/api/auth/login":
                self.login(self.read_json())
                return
            if path not in {"/api/reports", "/api/collections", "/api/waste", "/api/carbon"}:
                self.send_json(404, {"error": "Endpoint not found."})
                return
            self.authenticate()
            if not self.require_user():
                return
            data = self.read_json()
            if path == "/api/reports":
                self.create_report(data)
            elif path == "/api/collections":
                self.create_collection(data)
            elif path == "/api/waste":
                self.create_waste_entry(data)
            else:
                self.create_carbon_activity(data)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.IntegrityError as error:
            if path == "/api/auth/register":
                self.send_json(409, {"error": "An account with that email already exists."})
            else:
                LOGGER.info("Rejected invalid database reference for %s: %s", path, error)
                self.send_json(400, {"error": "The selected item is not available."})
        except sqlite3.Error:
            LOGGER.exception("Database error while handling POST %s", path)
            self.send_json(500, {"error": "The database could not save this item."})

    def do_PATCH(self):
        path = urlparse(self.path).path
        try:
            if not self.check_origin():
                self.send_json(403, {"error": "Cross-origin request rejected."})
                return
            self.authenticate()
            if not self.require_user():
                return
            data = self.read_json()
            if path == "/api/profile":
                self.update_profile(data)
                return
            match = re.fullmatch(r"/api/(reports|collections)/(\d+)", path)
            if not match:
                self.send_json(404, {"error": "Endpoint not found."})
                return
            resource, item_id = match.group(1), int(match.group(2))
            self.update_status(resource, item_id, data.get("status"))
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "That email address is already in use."})
        except sqlite3.Error:
            LOGGER.exception("Database error while handling PATCH %s", path)
            self.send_json(500, {"error": "The database could not update this item."})

    def do_DELETE(self):
        path = urlparse(self.path).path
        try:
            if not self.check_origin():
                self.send_json(403, {"error": "Cross-origin request rejected."})
                return
            self.authenticate()
            if not self.require_user():
                return
            match = re.fullmatch(r"/api/(waste|carbon)/(\d+)", path)
            if not match:
                self.send_json(404, {"error": "Endpoint not found."})
                return
            table = "waste_entries" if match.group(1) == "waste" else "carbon_activities"
            with db.connect_database() as connection:
                result = connection.execute(
                    f"DELETE FROM {table} WHERE id = ? AND user_id = ?",
                    (int(match.group(2)), self.current_user["id"]),
                )
            if result.rowcount == 0:
                self.send_json(404, {"error": "Entry not found."})
            else:
                self.send_json(200, {"deleted": True})
        except sqlite3.Error:
            LOGGER.exception("Database error while handling DELETE %s", path)
            self.send_json(500, {"error": "The database could not delete this item."})

    def register(self, data):
        display_name = self.required_text(data, "display_name", "Name", 80)
        email = self.required_text(data, "email", "Email", 254).lower()
        password = data.get("password")
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        if not isinstance(password, str) or not (
            PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
        ):
            raise ValueError(
                f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters."
            )
        salt, password_hash = hash_password(password)
        with db.connect_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (email, display_name, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, display_name, salt, password_hash, utc_now()),
            )
            user = {"id": cursor.lastrowid, "email": email, "display_name": display_name}
            token = self.create_session(connection, user)
        self.send_session(user, token, 201)

    def login(self, data):
        email = data.get("email")
        password = data.get("password")
        if not isinstance(email, str) or not isinstance(password, str) or len(password) > PASSWORD_MAX_LENGTH:
            self.send_json(401, {"error": "Email or password is incorrect."})
            return
        with db.connect_database() as connection:
            row = connection.execute(
                """
                SELECT id, email, display_name, password_salt, password_hash
                FROM users WHERE email = ?
                """,
                (email.strip().lower(),),
            ).fetchone()
            matches = verify_password(
                password,
                row["password_salt"] if row else DUMMY_PASSWORD_SALT,
                row["password_hash"] if row else DUMMY_PASSWORD_HASH,
            )
            if not row or not matches:
                self.send_json(401, {"error": "Email or password is incorrect."})
                return
            user = {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
            token = self.create_session(connection, user)
        self.send_session(user, token, 200)

    def create_session(self, connection, user):
        token = new_session_token()
        token_hash = session_token_digest(token)
        now = int(time.time())
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token_hash, user["id"], now + SESSION_MAX_AGE, utc_now()),
        )
        return token

    def send_session(self, user, token, status):
        body = json.dumps({"user": user}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_cookie(token)
        self.end_headers()
        self.wfile.write(body)

    def logout(self):
        self.authenticate()
        if self.session_hash:
            with db.connect_database() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?", (self.session_hash,)
                )
        body = json.dumps({"logged_out": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_cleared_cookie()
        self.end_headers()
        self.wfile.write(body)

    def update_profile(self, data):
        display_name = self.required_text(data, "display_name", "Name", 80)
        email = self.required_text(data, "email", "Email", 254).lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        user_id = self.current_user["id"]
        with db.connect_database() as connection:
            row = connection.execute(
                "SELECT password_salt, password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            update_password = "new_password" in data and data["new_password"] != ""
            values = [display_name, email]
            query = "UPDATE users SET display_name = ?, email = ?"
            if update_password:
                current_password = data.get("current_password")
                new_password = data.get("new_password")
                if not isinstance(current_password, str) or not verify_password(
                    current_password, row["password_salt"], row["password_hash"]
                ):
                    raise ValueError("Current password is incorrect.")
                if not isinstance(new_password, str) or not (
                    PASSWORD_MIN_LENGTH <= len(new_password) <= PASSWORD_MAX_LENGTH
                ):
                    raise ValueError(
                        f"New password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters."
                    )
                salt, password_hash = hash_password(new_password)
                query += ", password_salt = ?, password_hash = ?"
                values.extend((salt, password_hash))
            query += " WHERE id = ?"
            values.append(user_id)
            connection.execute(query, values)
            if update_password:
                connection.execute(
                    "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                    (user_id, self.session_hash),
                )
            user = connection.execute(
                "SELECT id, email, display_name FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        self.current_user = dict(user)
        self.send_json(200, {"user": self.current_user})

    def get_categories(self, user_id):
        with db.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.name, c.color, COUNT(w.id) AS entry_count
                FROM categories c
                LEFT JOIN waste_entries w ON w.category_id = c.id AND w.user_id = ?
                GROUP BY c.id ORDER BY c.id
                """,
                (user_id,),
            ).fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def get_reports(self, user_id):
        with db.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.title, r.location, r.description, r.urgency,
                       r.status, r.created_at, c.name AS category, c.color AS category_color
                FROM reports r JOIN categories c ON c.id = r.category_id
                WHERE r.user_id = ? ORDER BY r.created_at DESC, r.id DESC
                """,
                (user_id,),
            ).fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def get_collections(self, user_id):
        with db.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT id, report_id, area, scheduled_date, assigned_to, status, created_at
                FROM collections WHERE user_id = ? ORDER BY scheduled_date, id
                """,
                (user_id,),
            ).fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def get_waste(self, user_id):
        with db.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT w.id, w.category_id, c.name AS category, c.color AS category_color,
                       w.weight_kg, w.recycled_kg, w.note, w.created_at
                FROM waste_entries w JOIN categories c ON c.id = w.category_id
                WHERE w.user_id = ? ORDER BY w.created_at DESC, w.id DESC
                """,
                (user_id,),
            ).fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def get_carbon(self, user_id):
        with db.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT id, activity_type, quantity, unit, emissions_kg, note, created_at
                FROM carbon_activities WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
        activities = []
        for row in rows:
            activity = dict(row)
            activity["label"] = ACTIVITY_TYPES[activity["activity_type"]]["label"]
            activities.append(activity)
        self.send_json(200, activities)

    def get_recycling(self, user_id):
        with db.connect_database() as connection:
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(weight_kg), 0) AS waste_kg,
                       COALESCE(SUM(recycled_kg), 0) AS recycled_kg
                FROM waste_entries WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT w.id, c.name AS category, c.color AS category_color,
                       w.recycled_kg, w.note, w.created_at
                FROM waste_entries w JOIN categories c ON c.id = w.category_id
                WHERE w.user_id = ? AND w.recycled_kg > 0
                ORDER BY w.created_at DESC, w.id DESC LIMIT 10
                """,
                (user_id,),
            ).fetchall()
        waste_kg = float(totals["waste_kg"])
        recycled_kg = float(totals["recycled_kg"])
        self.send_json(
            200,
            {
                "waste_kg": waste_kg,
                "recycled_kg": recycled_kg,
                "diversion_rate": round(recycled_kg / waste_kg * 100, 1) if waste_kg else 0,
                "recent": [dict(row) for row in rows],
                "guidance": [
                    {"category": name, "detail": detail}
                    for name, detail in MATERIAL_GUIDANCE.items()
                ],
            },
        )

    def get_analytics(self, user_id):
        with db.connect_database() as connection:
            monthly = self.monthly_totals(connection, user_id)
            categories = connection.execute(
                """
                SELECT c.name, c.color, COALESCE(SUM(w.weight_kg), 0) AS weight_kg,
                       COALESCE(SUM(w.recycled_kg), 0) AS recycled_kg
                FROM categories c LEFT JOIN waste_entries w
                    ON w.category_id = c.id AND w.user_id = ?
                GROUP BY c.id ORDER BY weight_kg DESC, c.id
                """,
                (user_id,),
            ).fetchall()
            activities = connection.execute(
                """
                SELECT activity_type, COUNT(*) AS entry_count,
                       SUM(emissions_kg) AS emissions_kg
                FROM carbon_activities WHERE user_id = ?
                GROUP BY activity_type ORDER BY emissions_kg DESC
                """,
                (user_id,),
            ).fetchall()
        self.send_json(
            200,
            {
                "monthly": monthly,
                "waste_categories": [dict(row) for row in categories],
                "carbon_activities": [
                    {
                        **dict(row),
                        "label": ACTIVITY_TYPES[row["activity_type"]]["label"],
                    }
                    for row in activities
                ],
            },
        )

    def monthly_totals(self, connection, user_id):
        months = month_keys()
        first_month = months[0]["key"]
        carbon_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 7) AS month, SUM(emissions_kg) AS kg
            FROM carbon_activities
            WHERE user_id = ? AND substr(created_at, 1, 7) >= ?
            GROUP BY month
            """,
            (user_id, first_month),
        ).fetchall()
        waste_rows = connection.execute(
            """
            SELECT substr(created_at, 1, 7) AS month,
                   SUM(weight_kg) AS weight_kg, SUM(recycled_kg) AS recycled_kg
            FROM waste_entries
            WHERE user_id = ? AND substr(created_at, 1, 7) >= ?
            GROUP BY month
            """,
            (user_id, first_month),
        ).fetchall()
        carbon = {row["month"]: float(row["kg"] or 0) for row in carbon_rows}
        waste = {
            row["month"]: (float(row["weight_kg"] or 0), float(row["recycled_kg"] or 0))
            for row in waste_rows
        }
        return [
            {
                **month,
                "carbon_kg": round(carbon.get(month["key"], 0), 2),
                "waste_kg": round(waste.get(month["key"], (0, 0))[0], 2),
                "recycled_kg": round(waste.get(month["key"], (0, 0))[1], 2),
            }
            for month in months
        ]

    def get_dashboard(self, user_id):
        with db.connect_database() as connection:
            waste = connection.execute(
                """
                SELECT COALESCE(SUM(weight_kg), 0) AS weight_kg,
                       COALESCE(SUM(recycled_kg), 0) AS recycled_kg,
                       COUNT(*) AS entry_count
                FROM waste_entries WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            carbon = connection.execute(
                """
                SELECT COALESCE(SUM(emissions_kg), 0) AS lifetime_kg, COUNT(*) AS entry_count,
                       COALESCE(SUM(CASE WHEN substr(created_at, 1, 7) = ? THEN emissions_kg
                                   ELSE 0 END), 0) AS month_kg
                FROM carbon_activities WHERE user_id = ?
                """,
                (date.today().strftime("%Y-%m"), user_id),
            ).fetchone()
            reports = connection.execute(
                """
                SELECT r.id, r.title, r.location, r.urgency, r.status, r.created_at,
                       c.name AS category, c.color AS category_color
                FROM reports r JOIN categories c ON c.id = r.category_id
                WHERE r.user_id = ? ORDER BY r.created_at DESC, r.id DESC LIMIT 5
                """,
                (user_id,),
            ).fetchall()
            collections = connection.execute(
                """
                SELECT id, area, scheduled_date, assigned_to, status
                FROM collections WHERE user_id = ? AND status != 'completed'
                ORDER BY scheduled_date, id LIMIT 5
                """,
                (user_id,),
            ).fetchall()
            report_counts = connection.execute(
                """
                SELECT (SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'open')
                           AS open_reports,
                       (SELECT COUNT(*) FROM collections WHERE user_id = ?
                           AND status IN ('scheduled', 'in_progress')) AS active_collections,
                       (SELECT COUNT(*) FROM collections WHERE user_id = ?
                           AND status = 'completed') AS completed_collections
                """,
                (user_id, user_id, user_id),
            ).fetchone()
            category_rows = connection.execute(
                """
                SELECT c.name, c.color, COALESCE(SUM(w.weight_kg), 0) AS weight_kg
                FROM categories c LEFT JOIN waste_entries w
                    ON w.category_id = c.id AND w.user_id = ?
                GROUP BY c.id ORDER BY weight_kg DESC, c.id
                """,
                (user_id,),
            ).fetchall()
            activity_count = waste["entry_count"] + carbon["entry_count"]
            recent_waste = connection.execute(
                """
                SELECT 'waste' AS kind, c.name AS title, w.weight_kg AS quantity,
                       w.created_at, c.color
                FROM waste_entries w JOIN categories c ON c.id = w.category_id
                WHERE w.user_id = ? ORDER BY w.created_at DESC, w.id DESC LIMIT 5
                """,
                (user_id,),
            ).fetchall()
            recent_carbon = connection.execute(
                """
                SELECT 'carbon' AS kind, activity_type AS title, emissions_kg AS quantity,
                       created_at, 'carbon' AS color
                FROM carbon_activities WHERE user_id = ?
                ORDER BY created_at DESC, id DESC LIMIT 5
                """,
                (user_id,),
            ).fetchall()
            recent_activities = sorted(
                [dict(row) for row in (*recent_waste, *recent_carbon)],
                key=lambda item: item["created_at"],
                reverse=True,
            )[:6]
            monthly = self.monthly_totals(connection, user_id)

        waste_kg = float(waste["weight_kg"])
        recycled_kg = float(waste["recycled_kg"])
        diversion_rate = round(recycled_kg / waste_kg * 100, 1) if waste_kg else 0
        month_emissions = float(carbon["month_kg"])
        dominant = next(
            (row["name"] for row in category_rows if float(row["weight_kg"]) > 0), None
        )
        self.send_json(
            200,
            {
                "user": self.current_user,
                "summary": {
                    **dict(report_counts),
                    "waste_kg": round(waste_kg, 2),
                    "recycled_kg": round(recycled_kg, 2),
                    "diversion_rate": diversion_rate,
                    "carbon_kg": round(float(carbon["lifetime_kg"]), 2),
                    "month_carbon_kg": round(month_emissions, 2),
                    "sustainability_score": sustainability_score(
                        month_emissions, diversion_rate, activity_count > 0
                    ),
                    "waste_entries": waste["entry_count"],
                    "carbon_entries": carbon["entry_count"],
                },
                "recent_reports": [dict(row) for row in reports],
                "upcoming_collections": [dict(row) for row in collections],
                "category_breakdown": [dict(row) for row in category_rows],
                "monthly": monthly,
                "recent_activities": recent_activities,
                "recommendations": recommendations(
                    month_emissions, diversion_rate, dominant, activity_count > 0
                ),
            },
        )

    def get_analytics_csv(self, user_id):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Record type", "Date", "Activity or category", "Quantity", "Unit", "CO2e kg"])
        with db.connect_database() as connection:
            waste = connection.execute(
                """
                SELECT w.created_at, c.name, w.weight_kg, w.recycled_kg
                FROM waste_entries w JOIN categories c ON c.id = w.category_id
                WHERE w.user_id = ? ORDER BY w.created_at DESC
                """,
                (user_id,),
            ).fetchall()
            carbon = connection.execute(
                """
                SELECT created_at, activity_type, quantity, unit, emissions_kg
                FROM carbon_activities WHERE user_id = ? ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        for row in waste:
            writer.writerow(
                ["Waste", row["created_at"], row["name"], row["weight_kg"], "kg", ""]
            )
            if row["recycled_kg"]:
                writer.writerow(
                    ["Recycling", row["created_at"], row["name"], row["recycled_kg"], "kg", ""]
                )
        for row in carbon:
            writer.writerow(
                [
                    "Carbon",
                    row["created_at"],
                    ACTIVITY_TYPES[row["activity_type"]]["label"],
                    row["quantity"],
                    row["unit"],
                    row["emissions_kg"],
                ]
            )
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="ecotrack-impact.csv"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def create_waste_entry(self, data):
        category_id = data.get("category_id")
        if not isinstance(category_id, int) or isinstance(category_id, bool):
            raise ValueError("Choose a waste category.")
        weight = bounded_number(data, "weight_kg", "Waste amount", 100_000)
        recycled = data.get("recycled_kg", 0)
        if isinstance(recycled, bool) or not isinstance(recycled, (int, float)):
            raise ValueError("Recycled amount must be a number.")
        if not math.isfinite(recycled) or recycled < 0 or recycled > weight:
            raise ValueError("Recycled amount must be between 0 and the total waste amount.")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note.strip()) > 300:
            raise ValueError("Notes must be 300 characters or fewer.")
        with db.connect_database() as connection:
            exists = connection.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
            if not exists:
                raise ValueError("Choose a valid waste category.")
            cursor = connection.execute(
                """
                INSERT INTO waste_entries
                    (user_id, category_id, weight_kg, recycled_kg, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.current_user["id"],
                    category_id,
                    weight,
                    float(recycled),
                    note.strip(),
                    utc_now(),
                ),
            )
            row = connection.execute(
                """
                SELECT w.id, w.category_id, c.name AS category, c.color AS category_color,
                       w.weight_kg, w.recycled_kg, w.note, w.created_at
                FROM waste_entries w JOIN categories c ON c.id = w.category_id WHERE w.id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
        self.send_json(201, dict(row))

    def create_carbon_activity(self, data):
        activity_type = data.get("activity_type")
        if not isinstance(activity_type, str) or activity_type not in ACTIVITY_TYPES:
            raise ValueError("Choose a valid activity.")
        activity = ACTIVITY_TYPES[activity_type]
        quantity = bounded_number(data, "quantity", "Activity amount", 1_000_000)
        note = data.get("note", "")
        if not isinstance(note, str) or len(note.strip()) > 300:
            raise ValueError("Notes must be 300 characters or fewer.")
        emissions_kg = quantity * activity["factor"]
        with db.connect_database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO carbon_activities
                    (user_id, activity_type, quantity, unit, emissions_kg, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.current_user["id"],
                    activity_type,
                    quantity,
                    activity["unit"],
                    emissions_kg,
                    note.strip(),
                    utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT id, activity_type, quantity, unit, emissions_kg, note, created_at "
                "FROM carbon_activities WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        self.send_json(201, {**dict(row), "label": activity["label"]})

    def create_report(self, data):
        title = self.required_text(data, "title", "Report title", 120)
        location = self.required_text(data, "location", "Location", 180)
        description = self.required_text(data, "description", "Details", 1000)
        urgency = data.get("urgency", "medium")
        if not isinstance(urgency, str) or urgency not in {"low", "medium", "high"}:
            raise ValueError("Choose a valid urgency.")
        category = data.get("category")
        if not isinstance(category, int) or isinstance(category, bool):
            raise ValueError("Choose a waste category.")
        with db.connect_database() as connection:
            exists = connection.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category,)
            ).fetchone()
            if not exists:
                raise ValueError("Choose a valid waste category.")
            cursor = connection.execute(
                """
                INSERT INTO reports
                    (user_id, title, category_id, location, description, urgency, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.current_user["id"],
                    title,
                    category,
                    location,
                    description,
                    urgency,
                    utc_now(),
                ),
            )
            report_id = cursor.lastrowid
            row = connection.execute(
                """
                SELECT r.id, r.title, r.location, r.description, r.urgency,
                       r.status, r.created_at, c.name AS category, c.color AS category_color
                FROM reports r JOIN categories c ON c.id = r.category_id WHERE r.id = ?
                """,
                (report_id,),
            ).fetchone()
        self.send_json(201, dict(row))

    def create_collection(self, data):
        area = self.required_text(data, "area", "Pickup area", 180)
        assigned_to = self.required_text(data, "assigned_to", "Assigned team", 120)
        scheduled_date = data.get("scheduled_date")
        if not isinstance(scheduled_date, str):
            raise ValueError("Choose a pickup date.")
        try:
            date.fromisoformat(scheduled_date)
        except ValueError as error:
            raise ValueError("Enter a valid pickup date.") from error
        report_id = data.get("report_id")
        if report_id == "":
            report_id = None
        if report_id is not None and (
            not isinstance(report_id, int) or isinstance(report_id, bool)
        ):
            raise ValueError("Choose a valid linked report.")
        with db.connect_database() as connection:
            if report_id is not None:
                report = connection.execute(
                    "SELECT status FROM reports WHERE id = ? AND user_id = ?",
                    (report_id, self.current_user["id"]),
                ).fetchone()
                if not report:
                    raise ValueError("The linked report does not exist.")
                if report["status"] == "resolved":
                    raise ValueError("A resolved report cannot be linked to a new pickup.")
            cursor = connection.execute(
                """
                INSERT INTO collections
                    (user_id, report_id, area, scheduled_date, assigned_to, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.current_user["id"], report_id, area, scheduled_date, assigned_to, utc_now()),
            )
            if report_id is not None:
                connection.execute(
                    "UPDATE reports SET status = 'scheduled' WHERE id = ? AND status = 'open'",
                    (report_id,),
                )
            row = connection.execute(
                "SELECT * FROM collections WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        self.send_json(201, dict(row))

    def update_status(self, resource, item_id, status):
        allowed = REPORT_STATUSES if resource == "reports" else COLLECTION_STATUSES
        if not isinstance(status, str) or status not in allowed:
            raise ValueError("Choose a valid status.")
        user_id = self.current_user["id"]
        with db.connect_database() as connection:
            cursor = connection.execute(
                f"UPDATE {resource} SET status = ? WHERE id = ? AND user_id = ?",
                (status, item_id, user_id),
            )
            if cursor.rowcount == 0:
                self.send_json(404, {"error": "Item not found."})
                return
            if resource == "collections":
                collection = connection.execute(
                    "SELECT report_id FROM collections WHERE id = ? AND user_id = ?",
                    (item_id, user_id),
                ).fetchone()
                if collection["report_id"] is not None:
                    if status == "completed":
                        connection.execute(
                            """
                            UPDATE reports
                            SET status = CASE WHEN EXISTS (
                                SELECT 1 FROM collections
                                WHERE report_id = ? AND user_id = ?
                                    AND status IN ('scheduled', 'in_progress')
                            ) THEN 'scheduled' ELSE 'resolved' END
                            WHERE id = ? AND user_id = ?
                            """,
                            (collection["report_id"], user_id, collection["report_id"], user_id),
                        )
                    else:
                        connection.execute(
                            "UPDATE reports SET status = 'scheduled' WHERE id = ? AND user_id = ?",
                            (collection["report_id"], user_id),
                        )
            row = connection.execute(
                f"SELECT * FROM {resource} WHERE id = ? AND user_id = ?", (item_id, user_id)
            ).fetchone()
        self.send_json(200, dict(row))

    def serve_static(self, path):
        if path in {"", "/"}:
            path = "/index.html"
        requested = (STATIC_DIR / path.lstrip("/")).resolve()
        if not requested.is_relative_to(STATIC_DIR.resolve()) or not requested.is_file():
            self.send_json(404, {"error": "Page not found."})
            return
        content_type = {
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(requested.suffix, "application/octet-stream")
        body = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def main():
    db.initialize_database()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), EcoTrackHandler)
    LOGGER.info("EcoTrack is running at http://127.0.0.1:%s", port)
    LOGGER.info("SQLite database: %s", db.DB_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("EcoTrack server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
