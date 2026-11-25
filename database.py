
import hashlib
import hmac
import secrets
import re
import csv
import io
import tomllib
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

import psycopg


# =========================================================
# CONFIGURATION AND DATABASE CONNECTION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"


def _get_database_settings():
    """Read database credentials from Streamlit secrets or local TOML."""

    try:
        import streamlit as st
        settings = st.secrets.get("database", {})
        if settings and settings.get("host"):
            return dict(settings)
    except Exception:
        pass

    if SECRETS_PATH.exists():
        with open(SECRETS_PATH, "rb") as file:
            secrets_data = tomllib.load(file)
        return secrets_data["database"]

    raise RuntimeError(
        "Database configuration is missing. "
        "Configure the database section in Streamlit secrets."
    )


def connect_db():
    """Connect to the Supabase PostgreSQL database."""

    settings = _get_database_settings()

    return psycopg.connect(
        host=settings["host"],
        port=int(settings["port"]),
        dbname=settings["dbname"],
        user=settings["user"],
        password=settings["password"],
        sslmode=settings.get("sslmode", "require"),
        connect_timeout=15
    )


@contextmanager
def _db():
    """Manage a database connection and transaction safely."""

    connection = connect_db()

    try:
        with connection.transaction():
            yield connection
    finally:
        connection.close()


def create_tables():
    """
    Supabase tables were already created and migrated.
    Do not recreate or alter the cloud schema.
    """

    return True


# =========================================================
# PASSWORD SECURITY
# =========================================================

def hash_password(password):
    salt = secrets.token_bytes(16)

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200000
    )

    return salt.hex() + ":" + hashed.hex()


def verify_password(password, stored_password):
    try:
        salt_hex, hash_hex = stored_password.split(":")

        salt = bytes.fromhex(salt_hex)
        stored_hash = bytes.fromhex(hash_hex)

        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            200000
        )

        return hmac.compare_digest(
            calculated_hash,
            stored_hash
        )

    except (ValueError, TypeError, AttributeError):
        return False


# =========================================================
# ADMIN ACCOUNTS
# =========================================================

def create_admin(username, password):
    username = (username or "").strip()

    if not username or len(password) < 8:
        return False

    try:
        with _db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO admins
                    (username, password_hash, created_at)
                    VALUES (%s, %s, %s)
                """, (
                    username,
                    hash_password(password),
                    datetime.now().isoformat(timespec="seconds")
                ))

        return True

    except psycopg.IntegrityError:
        return False


def login_admin(username, password):
    try:
        with _db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT password_hash
                    FROM admins
                    WHERE username = %s
                """, ((username or "").strip(),))

                record = cursor.fetchone()

                return bool(
                    record
                    and verify_password(password, record[0])
                )

    except psycopg.Error:
        return False


def get_admins():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT username
                FROM admins
                ORDER BY username
            """)

            return [row[0] for row in cursor.fetchall()]


def admin_exists():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM admins
                )
            """)

            return cursor.fetchone()[0]


# =========================================================
# STUDENT VERIFICATION
# =========================================================

CATEGORY_ALIASES = {
    "UG": "UG",
    "UNDERGRADUATE": "UG",
    "PG": "PG",
    "POSTGRADUATE": "PG",
    "DR": "Doctorate",
    "DOCTORATE": "Doctorate",
    "PHD": "Doctorate",
    "PROFESSOR": "Professor",
    "FACULTY": "Professor",
    "PROF": "Professor",
}


def normalize_category(category):
    if not category:
        return None

    return CATEGORY_ALIASES.get(
        category.strip().upper()
    )


def normalize_registration_number(registration_number):
    if not registration_number:
        return ""

    return registration_number.strip().upper()


def validate_registration_format(registration_number, category):
    registration_number = normalize_registration_number(
        registration_number
    )

    category = normalize_category(category)

    if category in ("UG", "PG", "Doctorate"):
        if not re.fullmatch(
            r"^\d{2}(UG|PG|DR)\d{5}$",
            registration_number
        ):
            return False

        expected = {
            "UG": "UG",
            "PG": "PG",
            "Doctorate": "DR"
        }

        return registration_number[2:4] == expected[category]

    if category == "Professor":
        return (
            len(registration_number) >= 4
            and re.fullmatch(
                r"[A-Z0-9-]+",
                registration_number
            ) is not None
        )

    return False


def import_verified_records(csv_text):
    try:
        reader = csv.DictReader(
            io.StringIO(csv_text.lstrip("\ufeff"))
        )

        required_columns = {
            "registration_number",
            "full_name",
            "category",
            "joining_year"
        }

        if not reader.fieldnames:
            return 0, ["CSV file is empty."]

        actual_columns = {
            field.strip().lower()
            for field in reader.fieldnames
            if field
        }

        if not required_columns.issubset(actual_columns):
            return 0, [
                "CSV must contain: registration_number, "
                "full_name, category, joining_year"
            ]

        rows = []

        for row in reader:
            normalized_row = {
                (key or "").strip().lower():
                    (value or "").strip()
                for key, value in row.items()
            }

            reg_no = normalize_registration_number(
                normalized_row.get("registration_number")
            )

            full_name = normalized_row.get("full_name")

            category = normalize_category(
                normalized_row.get("category")
            )

            year_text = normalized_row.get("joining_year")

            if not reg_no or not full_name or not category:
                continue

            try:
                joining_year = int(year_text)
            except (TypeError, ValueError):
                joining_year = None

            if category in ("UG", "PG", "Doctorate"):
                if not validate_registration_format(
                    reg_no,
                    category
                ):
                    continue

            rows.append((
                reg_no,
                full_name,
                category,
                joining_year
            ))

    except Exception as error:
        return 0, [f"Could not read CSV: {error}"]

    imported = 0
    errors = []

    try:
        with _db() as connection:
            with connection.cursor() as cursor:
                for reg_no, full_name, category, joining_year in rows:

                    cursor.execute("""
                        INSERT INTO verified_students
                        (
                            registration_number,
                            full_name,
                            category,
                            joining_year,
                            registered_username,
                            imported_at
                        )
                        VALUES (%s, %s, %s, %s, NULL, %s)
                        ON CONFLICT (registration_number)
                        DO UPDATE SET
                            full_name = EXCLUDED.full_name,
                            category = EXCLUDED.category,
                            joining_year = EXCLUDED.joining_year,
                            imported_at = EXCLUDED.imported_at
                    """, (
                        reg_no,
                        full_name,
                        category,
                        joining_year,
                        datetime.now().isoformat(timespec="seconds")
                    ))

                    imported += 1

    except psycopg.Error as error:
        errors.append(str(error))
        imported = 0

    return imported, errors


def get_verified_student_record(registration_number):
    reg_no = normalize_registration_number(
        registration_number
    )

    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    registration_number,
                    full_name,
                    category,
                    joining_year,
                    registered_username
                FROM verified_students
                WHERE registration_number = %s
            """, (reg_no,))

            return cursor.fetchone()


def verify_registration(registration_number, category, full_name):
    reg_no = normalize_registration_number(
        registration_number
    )

    category = normalize_category(category)
    full_name = (full_name or "").strip()

    record = None
    result = "FAILED"

    try:
        with _db() as connection:
            with connection.cursor() as cursor:

                if not validate_registration_format(
                    reg_no,
                    category
                ):
                    message = (
                        "Registration number format or "
                        "category is invalid."
                    )

                else:
                    cursor.execute("""
                        SELECT
                            registration_number,
                            full_name,
                            category,
                            joining_year,
                            registered_username
                        FROM verified_students
                        WHERE registration_number = %s
                    """, (reg_no,))

                    record = cursor.fetchone()

                    if not record:
                        message = (
                            "Registration number not found in the "
                            "official verification database."
                        )

                    elif normalize_category(record[2]) != category:
                        message = (
                            "The selected category does not match "
                            "the official university record."
                        )

                    elif record[4]:
                        message = (
                            "This registration number has already "
                            "been used to create a CampusConnect account."
                        )

                    elif (
                        record[1].strip().casefold()
                        != full_name.casefold()
                    ):
                        message = (
                            "Name does not match the official "
                            "university record. Please enter your "
                            "name as registered with the university."
                        )

                    else:
                        result = "SUCCESS"
                        message = "Student verified successfully."

                cursor.execute("""
                    INSERT INTO verification_logs
                    (
                        registration_number,
                        category,
                        result,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s)
                """, (
                    reg_no,
                    category or "",
                    result,
                    datetime.now().isoformat(timespec="seconds")
                ))

        return result == "SUCCESS", message, record

    except psycopg.Error as error:
        return False, f"Verification could not be completed: {error}", None


def complete_verified_registration(
    registration_number,
    username,
    password,
    full_name,
    category,
    programme,
    year,
    bio,
    skills
):
    reg_no = normalize_registration_number(
        registration_number
    )

    category = normalize_category(category)
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    programme = (programme or "").strip()
    bio = bio or ""
    skills = skills or ""

    if not username or len(password) < 8:
        return False, (
            "Username is required and password must be "
            "at least 8 characters."
        )

    if not validate_registration_format(reg_no, category):
        return False, "Registration number format or category is invalid."

    try:
        joining_year = int(year)
    except (ValueError, TypeError):
        return False, "Please enter a valid joining year."

    try:
        with _db() as connection:
            with connection.cursor() as cursor:

                # Lock the official record to prevent two
                # simultaneous registrations claiming it.
                cursor.execute("""
                    SELECT
                        full_name,
                        category,
                        registered_username
                    FROM verified_students
                    WHERE registration_number = %s
                    FOR UPDATE
                """, (reg_no,))

                official_record = cursor.fetchone()

                if not official_record:
                    return False, "Registration number not found."

                if official_record[2]:
                    return False, (
                        "This registration number is already registered."
                    )

                if (
                    official_record[0].strip().casefold()
                    != full_name.casefold()
                ):
                    return False, "Name does not match official record."

                if normalize_category(official_record[1]) != category:
                    return False, (
                        "Category does not match official record."
                    )

                hashed_password = hash_password(password)

                cursor.execute("""
                    INSERT INTO students
                    (
                        username,
                        password,
                        name,
                        programme,
                        year,
                        bio,
                        skills,
                        registration_number,
                        category,
                        verified
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                """, (
                    username,
                    hashed_password,
                    full_name,
                    programme,
                    joining_year,
                    bio,
                    skills,
                    reg_no,
                    category
                ))

                cursor.execute("""
                    UPDATE verified_students
                    SET registered_username = %s
                    WHERE registration_number = %s
                    AND registered_username IS NULL
                """, (username, reg_no))

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Verification record was already claimed."
                    )

        return True, "Verified account created successfully."

    except psycopg.IntegrityError as error:
        error_text = str(error).lower()

        if "students_pkey" in error_text or "username" in error_text:
            return False, "Username already exists."

        if "registration_number" in error_text:
            return False, "This registration number is already registered."

        return False, f"Registration failed: {error}"

    except Exception as error:
        return False, f"Registration failed: {error}"


def get_verified_records():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    registration_number,
                    full_name,
                    category,
                    joining_year,
                    registered_username,
                    imported_at
                FROM verified_students
                ORDER BY registration_number
            """)

            return cursor.fetchall()


def get_verification_logs(limit=100):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    log_id,
                    registration_number,
                    category,
                    result,
                    created_at
                FROM verification_logs
                ORDER BY log_id DESC
                LIMIT %s
            """, (int(limit),))

            return cursor.fetchall()


def delete_verified_record(registration_number):
    reg_no = normalize_registration_number(
        registration_number
    )

    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM verified_students
                WHERE registration_number = %s
                AND registered_username IS NULL
            """, (reg_no,))

            return cursor.rowcount > 0


# =========================================================
# STUDENT ACCOUNTS
# =========================================================

def add_student(
    username,
    password,
    name,
    programme="",
    year=None,
    bio="",
    skills=""
):
    username = (username or "").strip()
    name = (name or "").strip()

    if not username or not name or len(password) < 8:
        return False

    try:
        with _db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO students
                    (
                        username,
                        password,
                        name,
                        programme,
                        year,
                        bio,
                        skills,
                        category,
                        verified
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'UG', 0)
                """, (
                    username,
                    hash_password(password),
                    name,
                    programme,
                    year,
                    bio,
                    skills
                ))

        return True

    except psycopg.IntegrityError:
        return False


def get_student(username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    username,
                    password,
                    name,
                    programme,
                    year,
                    bio,
                    skills,
                    profile_picture,
                    registration_number,
                    category,
                    verified
                FROM students
                WHERE username = %s
            """, (username,))

            return cursor.fetchone()


def update_student_profile(
    username,
    name,
    programme,
    year,
    bio,
    skills
):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE students
                SET
                    name = %s,
                    programme = %s,
                    year = %s,
                    bio = %s,
                    skills = %s
                WHERE username = %s
            """, (
                name,
                programme,
                year,
                bio,
                skills,
                username
            ))

            return cursor.rowcount > 0


def update_profile_picture(username, image_path):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE students
                SET profile_picture = %s
                WHERE username = %s
            """, (image_path, username))

            return cursor.rowcount > 0


def login_student(username, password):
    student = get_student(username)

    return bool(
        student
        and verify_password(password, student[1])
    )


# =========================================================
# CONNECTIONS AND REQUESTS
# =========================================================

def send_request(sender, receiver):
    if not sender or not receiver or sender == receiver:
        return False

    try:
        with _db() as connection:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT username
                    FROM students
                    WHERE username IN (%s, %s)
                """, (sender, receiver))

                if len(cursor.fetchall()) != 2:
                    return False

                first, second = sorted((sender, receiver))

                cursor.execute("""
                    SELECT 1
                    FROM connections
                    WHERE student1 = %s AND student2 = %s
                """, (first, second))

                if cursor.fetchone():
                    return False

                cursor.execute("""
                    SELECT 1
                    FROM pending_requests
                    WHERE
                        (sender = %s AND receiver = %s)
                        OR
                        (sender = %s AND receiver = %s)
                """, (sender, receiver, receiver, sender))

                if cursor.fetchone():
                    return False

                cursor.execute("""
                    INSERT INTO pending_requests
                    (sender, receiver)
                    VALUES (%s, %s)
                """, (sender, receiver))

        return True

    except psycopg.IntegrityError:
        return False


def accept_request(sender, receiver):
    first, second = sorted((sender, receiver))

    try:
        with _db() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 1
                    FROM pending_requests
                    WHERE sender = %s AND receiver = %s
                    FOR UPDATE
                """, (sender, receiver))

                if not cursor.fetchone():
                    return False

                cursor.execute("""
                    INSERT INTO connections
                    (student1, student2)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (first, second))

                cursor.execute("""
                    DELETE FROM pending_requests
                    WHERE sender = %s AND receiver = %s
                """, (sender, receiver))

        return True

    except psycopg.Error:
        return False


def reject_request(sender, receiver):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM pending_requests
                WHERE sender = %s AND receiver = %s
            """, (sender, receiver))

            return cursor.rowcount > 0


def cancel_request(sender, receiver):
    return reject_request(sender, receiver)


def remove_connection(student1, student2):
    first, second = sorted((student1, student2))

    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM connections
                WHERE student1 = %s AND student2 = %s
            """, (first, second))

            return cursor.rowcount > 0


def get_connections(username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT student2
                FROM connections
                WHERE student1 = %s

                UNION

                SELECT student1
                FROM connections
                WHERE student2 = %s
            """, (username, username))

            return {row[0] for row in cursor.fetchall()}


def get_pending_requests(username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sender
                FROM pending_requests
                WHERE receiver = %s
                ORDER BY sender
            """, (username,))

            return [row[0] for row in cursor.fetchall()]


def get_sent_requests(username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT receiver
                FROM pending_requests
                WHERE sender = %s
                ORDER BY receiver
            """, (username,))

            return [row[0] for row in cursor.fetchall()]


def get_all_students():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT username
                FROM students
                ORDER BY username
            """)

            return [row[0] for row in cursor.fetchall()]


def get_all_connections():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT student1, student2
                FROM connections
                ORDER BY student1, student2
            """)

            return cursor.fetchall()


# =========================================================
# POSTS
# =========================================================

def add_post(username, content, image_path=None):
    content = (content or "").strip()

    if not content and not image_path:
        return False

    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO posts
                (username, content, created_at, image_path)
                VALUES (%s, %s, %s, %s)
            """, (
                username,
                content,
                datetime.now().isoformat(timespec="seconds"),
                image_path
            ))

    return True


def get_all_posts():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    post_id,
                    username,
                    content,
                    created_at,
                    image_path
                FROM posts
                ORDER BY created_at DESC, post_id DESC
            """)

            return cursor.fetchall()


def delete_post(post_id, username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM posts
                WHERE post_id = %s AND username = %s
            """, (post_id, username))

            return cursor.rowcount > 0


# =========================================================
# LIKES
# =========================================================

def toggle_post_like(post_id, username):
    with _db() as connection:
        with connection.cursor() as cursor:

            cursor.execute("""
                DELETE FROM post_likes
                WHERE post_id = %s AND username = %s
                RETURNING post_id
            """, (post_id, username))

            if cursor.fetchone():
                return False

            cursor.execute("""
                INSERT INTO post_likes
                (post_id, username, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (post_id, username) DO NOTHING
                RETURNING post_id
            """, (
                post_id,
                username,
                datetime.now().isoformat(timespec="seconds")
            ))

            return cursor.fetchone() is not None


def get_post_like_count(post_id):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM post_likes
                WHERE post_id = %s
            """, (post_id,))

            return cursor.fetchone()[0]


def user_liked_post(post_id, username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM post_likes
                    WHERE post_id = %s AND username = %s
                )
            """, (post_id, username))

            return cursor.fetchone()[0]


# =========================================================
# COMMENTS
# =========================================================

def add_comment(post_id, username, comment_text):
    comment_text = (comment_text or "").strip()

    if not comment_text:
        return False

    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO post_comments
                (
                    post_id,
                    username,
                    comment_text,
                    created_at
                )
                VALUES (%s, %s, %s, %s)
            """, (
                post_id,
                username,
                comment_text,
                datetime.now().isoformat(timespec="seconds")
            ))

    return True


def get_post_comments(post_id):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    comment_id,
                    username,
                    comment_text,
                    created_at
                FROM post_comments
                WHERE post_id = %s
                ORDER BY comment_id
            """, (post_id,))

            return cursor.fetchall()


def delete_comment(comment_id, username):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM post_comments
                WHERE comment_id = %s AND username = %s
            """, (comment_id, username))

            return cursor.rowcount > 0


# =========================================================
# ADMIN DASHBOARD AND MODERATION
# =========================================================

def get_admin_statistics():
    with _db() as connection:
        with connection.cursor() as cursor:

            queries = {
                "students": "SELECT COUNT(*) FROM students",
                "connections": "SELECT COUNT(*) FROM connections",
                "posts": "SELECT COUNT(*) FROM posts",
                "likes": "SELECT COUNT(*) FROM post_likes",
                "comments": "SELECT COUNT(*) FROM post_comments",
                "verified": """
                    SELECT COUNT(*) FROM students WHERE verified = 1
                """,
                "unused_records": """
                    SELECT COUNT(*) FROM verified_students
                    WHERE registered_username IS NULL
                """
            }

            statistics = {}

            for key, query in queries.items():
                cursor.execute(query)
                statistics[key] = cursor.fetchone()[0]

            return statistics


def get_all_students_details():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    username,
                    name,
                    programme,
                    year,
                    bio,
                    skills,
                    profile_picture,
                    registration_number,
                    category,
                    verified
                FROM students
                ORDER BY LOWER(name)
            """)

            return cursor.fetchall()


def get_all_posts_admin():
    return get_all_posts()


def delete_post_admin(post_id):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM posts
                WHERE post_id = %s
            """, (post_id,))

            return cursor.rowcount > 0


def get_all_comments_admin():
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    comment_id,
                    post_id,
                    username,
                    comment_text,
                    created_at
                FROM post_comments
                ORDER BY comment_id DESC
            """)

            return cursor.fetchall()


def delete_comment_admin(comment_id):
    with _db() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM post_comments
                WHERE comment_id = %s
            """, (comment_id,))

            return cursor.rowcount > 0


def delete_student_admin(username):
    try:
        with _db() as connection:
            with connection.cursor() as cursor:

                cursor.execute("""
                    SELECT registration_number
                    FROM students
                    WHERE username = %s
                    FOR UPDATE
                """, (username,))

                student = cursor.fetchone()

                if not student:
                    return False

                registration_number = student[0]

                # Release the official verification claim.
                if registration_number:
                    cursor.execute("""
                        UPDATE verified_students
                        SET registered_username = NULL
                        WHERE registration_number = %s
                        AND registered_username = %s
                    """, (registration_number, username))

                # Delete student. Foreign-key cascades remove
                # associated posts, likes, comments and connections.
                cursor.execute("""
                    DELETE FROM students
                    WHERE username = %s
                """, (username,))

                return cursor.rowcount > 0

    except psycopg.Error:
        return False
