
import sqlite3
import hashlib
import hmac
import secrets
import re
import csv
import io
from pathlib import Path
from datetime import datetime


# Keep the database inside the project folder
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "campusconnect.db"


def connect_db():
    connection = sqlite3.connect(str(DB_PATH))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# =========================================================
# DATABASE INITIALIZATION AND SAFE MIGRATIONS
# =========================================================

def create_tables():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            programme TEXT,
            year INTEGER,
            bio TEXT,
            skills TEXT,
            profile_picture TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            student1 TEXT NOT NULL,
            student2 TEXT NOT NULL,
            PRIMARY KEY (student1, student2),
            CHECK (student1 < student2),
            FOREIGN KEY (student1) REFERENCES students(username),
            FOREIGN KEY (student2) REFERENCES students(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            PRIMARY KEY (sender, receiver),
            CHECK (sender != receiver),
            FOREIGN KEY (sender) REFERENCES students(username),
            FOREIGN KEY (receiver) REFERENCES students(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            image_path TEXT,
            FOREIGN KEY (username) REFERENCES students(username)
        )
    """)

    # FIXED: closing parenthesis added
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_likes (
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, username),
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
                ON DELETE CASCADE,
            FOREIGN KEY (username) REFERENCES students(username)
                ON DELETE CASCADE
        )
    """)

    # FIXED: closing parenthesis added
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_comments (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            comment_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
                ON DELETE CASCADE,
            FOREIGN KEY (username) REFERENCES students(username)
                ON DELETE CASCADE
        )
    """)

    # Add new student fields safely to existing database
    student_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(students)"
        ).fetchall()
    }

    if "profile_picture" not in student_columns:
        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN profile_picture TEXT
        """)

    if "registration_number" not in student_columns:
        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN registration_number TEXT
        """)

    if "category" not in student_columns:
        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN category TEXT DEFAULT 'UG'
        """)

    if "verified" not in student_columns:
        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN verified INTEGER DEFAULT 0
        """)

    post_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(posts)"
        ).fetchall()
    }

    if "image_path" not in post_columns:
        cursor.execute("""
            ALTER TABLE posts
            ADD COLUMN image_path TEXT
        """)

    # Admin accounts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Official records uploaded by authorized admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verified_students (
            registration_number TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            category TEXT NOT NULL,
            joining_year INTEGER,
            registered_username TEXT UNIQUE,
            imported_at TEXT NOT NULL
        )
    """)

    # Audit records; do not store passwords
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_number TEXT,
            category TEXT,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_students_registration_number
        ON students(registration_number)
        WHERE registration_number IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_posts_created_at
        ON posts(created_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_comments_post_id
        ON post_comments(post_id)
    """)

    connection.commit()
    connection.close()


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

        new_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            200000
        )

        return hmac.compare_digest(
            new_hash.hex(),
            hash_hex
        )

    except (ValueError, TypeError):
        return False


# =========================================================
# ADMIN FUNCTIONS
# =========================================================

def create_admin(username, password):
    username = username.strip()

    if not username or len(password) < 8:
        return False

    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO admins
            (username, password_hash, created_at)
            VALUES (?, ?, ?)
        """, (
            username,
            hash_password(password),
            datetime.now().isoformat(timespec="seconds")
        ))

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        connection.close()


def login_admin(username, password):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT password_hash
        FROM admins
        WHERE username = ?
    """, (username.strip(),))

    result = cursor.fetchone()
    connection.close()

    if not result:
        return False

    return verify_password(password, result[0])


def get_admins():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT admin_id, username, created_at
        FROM admins
        ORDER BY admin_id
    """)

    result = cursor.fetchall()
    connection.close()

    return result


def admin_exists():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM admins
    """)

    count = cursor.fetchone()[0]
    connection.close()

    return count > 0


# =========================================================
# OFFICIAL STUDENT RECORD IMPORT / VERIFICATION
# =========================================================

CATEGORY_ALIASES = {
    "UG": "UG",
    "UNDERGRADUATE": "UG",
    "UNDERGRAD": "UG",
    "PG": "PG",
    "POSTGRADUATE": "PG",
    "POSTGRAD": "PG",
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
        pattern = r"^\d{2}(UG|PG|DR)\d{5}$"

        if not re.fullmatch(pattern, registration_number):
            return False

        number_category = registration_number[2:4]

        expected = {
            "UG": "UG",
            "PG": "PG",
            "Doctorate": "DR"
        }

        return number_category == expected[category]

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
                (key or "").strip().lower(): (value or "").strip()
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

    connection = connect_db()
    cursor = connection.cursor()

    imported = 0
    errors = []

    try:
        for reg_no, full_name, category, joining_year in rows:
            cursor.execute("""
                SELECT registered_username
                FROM verified_students
                WHERE registration_number = ?
            """, (reg_no,))

            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE verified_students
                    SET
                        full_name = ?,
                        category = ?,
                        joining_year = ?,
                        imported_at = ?
                    WHERE registration_number = ?
                """, (
                    full_name,
                    category,
                    joining_year,
                    datetime.now().isoformat(timespec="seconds"),
                    reg_no
                ))

            else:
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
                    VALUES (?, ?, ?, ?, NULL, ?)
                """, (
                    reg_no,
                    full_name,
                    category,
                    joining_year,
                    datetime.now().isoformat(timespec="seconds")
                ))

            imported += 1

        connection.commit()

    except sqlite3.Error as error:
        connection.rollback()
        errors.append(str(error))

    finally:
        connection.close()

    return imported, errors


def get_verified_student_record(registration_number):
    reg_no = normalize_registration_number(
        registration_number
    )

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            registration_number,
            full_name,
            category,
            joining_year,
            registered_username
        FROM verified_students
        WHERE registration_number = ?
    """, (reg_no,))

    record = cursor.fetchone()
    connection.close()

    return record


def verify_registration(registration_number, category, full_name):
    reg_no = normalize_registration_number(
        registration_number
    )

    category = normalize_category(category)
    full_name = (full_name or "").strip()

    connection = connect_db()
    cursor = connection.cursor()

    record = None
    result = "FAILED"

    if not validate_registration_format(reg_no, category):
        message = "Registration number format or category is invalid."

    else:
        cursor.execute("""
            SELECT
                registration_number,
                full_name,
                category,
                joining_year,
                registered_username
            FROM verified_students
            WHERE registration_number = ?
        """, (reg_no,))

        record = cursor.fetchone()

        if not record:
            message = (
                "Registration number not found in the official "
                "verification database."
            )

        elif normalize_category(record[2]) != category:
            message = (
                "The selected category does not match the "
                "official university record."
            )

        elif record[4]:
            message = (
                "This registration number has already been used "
                "to create a CampusConnect account."
            )

        elif (
            record[1].strip().casefold()
            != full_name.casefold()
        ):
            message = (
                "Name does not match the official university record. "
                "Please enter your name as registered with the university."
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
        VALUES (?, ?, ?, ?)
    """, (
        reg_no,
        category or "",
        result,
        datetime.now().isoformat(timespec="seconds")
    ))

    connection.commit()
    connection.close()

    return result == "SUCCESS", message, record


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
        return False, "Username is required and password must be at least 8 characters."

    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                full_name,
                category,
                registered_username
            FROM verified_students
            WHERE registration_number = ?
        """, (reg_no,))

        official_record = cursor.fetchone()

        if not official_record:
            return False, "Registration number not found."

        if official_record[2]:
            return False, "This registration number is already registered."

        if (
            official_record[0].strip().casefold()
            != full_name.casefold()
        ):
            return False, "Name does not match official record."

        if normalize_category(official_record[1]) != category:
            return False, "Category does not match official record."

        cursor.execute("""
            SELECT username
            FROM students
            WHERE username = ?
        """, (username,))

        if cursor.fetchone():
            return False, "Username already exists."

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            username,
            hashed_password,
            full_name,
            programme,
            int(year),
            bio,
            skills,
            reg_no,
            category
        ))

        cursor.execute("""
            UPDATE verified_students
            SET registered_username = ?
            WHERE registration_number = ?
            AND registered_username IS NULL
        """, (username, reg_no))

        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError(
                "Verification record was already claimed."
            )

        connection.commit()
        return True, "Verified account created successfully."

    except sqlite3.IntegrityError as error:
        connection.rollback()
        return False, f"Registration failed: {error}"

    except Exception as error:
        connection.rollback()
        return False, f"Registration failed: {error}"

    finally:
        connection.close()


def get_verified_records():
    connection = connect_db()
    cursor = connection.cursor()

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

    records = cursor.fetchall()
    connection.close()

    return records


def get_verification_logs(limit=100):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            registration_number,
            category,
            result,
            created_at
        FROM verification_logs
        ORDER BY log_id DESC
        LIMIT ?
    """, (limit,))

    logs = cursor.fetchall()
    connection.close()

    return logs


def delete_verified_record(registration_number):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM verified_students
        WHERE registration_number = ?
        AND registered_username IS NULL
    """, (normalize_registration_number(registration_number),))

    deleted = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return deleted


# =========================================================
# STUDENT FUNCTIONS
# =========================================================

def add_student(
    username,
    password,
    name,
    programme,
    year,
    bio,
    skills
):
    connection = connect_db()
    cursor = connection.cursor()

    try:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, 'UG', 0)
        """, (
            username.strip(),
            hash_password(password),
            name.strip(),
            programme,
            int(year),
            bio,
            skills
        ))

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        connection.close()


def get_student(username):
    connection = connect_db()
    cursor = connection.cursor()

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
        WHERE username = ?
    """, (username,))

    student = cursor.fetchone()
    connection.close()

    return student


def update_student_profile(
    username,
    name,
    programme,
    year,
    bio,
    skills
):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE students
        SET
            name = ?,
            programme = ?,
            year = ?,
            bio = ?,
            skills = ?
        WHERE username = ?
    """, (
        name.strip(),
        programme.strip(),
        int(year),
        bio,
        skills,
        username
    ))

    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return updated


def update_profile_picture(username, image_path):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE students
        SET profile_picture = ?
        WHERE username = ?
    """, (image_path, username))

    updated = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return updated


def login_student(username, password):
    student = get_student(username)

    if not student:
        return False

    return verify_password(password, student[1])


# =========================================================
# CONNECTION REQUESTS
# =========================================================

def send_request(sender, receiver):
    connection = connect_db()
    cursor = connection.cursor()

    if sender == receiver:
        connection.close()
        return False

    cursor.execute("""
        SELECT username FROM students
        WHERE username IN (?, ?)
    """, (sender, receiver))

    if len(cursor.fetchall()) != 2:
        connection.close()
        return False

    first, second = sorted([sender, receiver])

    cursor.execute("""
        SELECT 1 FROM connections
        WHERE student1 = ? AND student2 = ?
    """, (first, second))

    if cursor.fetchone():
        connection.close()
        return False

    cursor.execute("""
        SELECT 1 FROM pending_requests
        WHERE (sender = ? AND receiver = ?)
        OR (sender = ? AND receiver = ?)
    """, (sender, receiver, receiver, sender))

    if cursor.fetchone():
        connection.close()
        return False

    try:
        cursor.execute("""
            INSERT INTO pending_requests
            (sender, receiver)
            VALUES (?, ?)
        """, (sender, receiver))

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        connection.close()


def accept_request(sender, receiver):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT 1 FROM pending_requests
        WHERE sender = ? AND receiver = ?
    """, (sender, receiver))

    if not cursor.fetchone():
        connection.close()
        return False

    first, second = sorted([sender, receiver])

    try:
        cursor.execute("""
            INSERT OR IGNORE INTO connections
            (student1, student2)
            VALUES (?, ?)
        """, (first, second))

        cursor.execute("""
            DELETE FROM pending_requests
            WHERE sender = ? AND receiver = ?
        """, (sender, receiver))

        connection.commit()
        return True

    except sqlite3.Error:
        connection.rollback()
        return False

    finally:
        connection.close()


def reject_request(sender, receiver):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM pending_requests
        WHERE sender = ? AND receiver = ?
    """, (sender, receiver))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


def cancel_request(sender, receiver):
    return reject_request(sender, receiver)


def remove_connection(student1, student2):
    connection = connect_db()
    cursor = connection.cursor()

    first, second = sorted([student1, student2])

    cursor.execute("""
        DELETE FROM connections
        WHERE student1 = ? AND student2 = ?
    """, (first, second))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


def get_connections(username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT student2 FROM connections
        WHERE student1 = ?

        UNION

        SELECT student1 FROM connections
        WHERE student2 = ?
    """, (username, username))

    result = cursor.fetchall()
    connection.close()

    return {row[0] for row in result}


def get_pending_requests(username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT sender
        FROM pending_requests
        WHERE receiver = ?
    """, (username,))

    result = cursor.fetchall()
    connection.close()

    return [row[0] for row in result]


def get_sent_requests(username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT receiver
        FROM pending_requests
        WHERE sender = ?
    """, (username,))

    result = cursor.fetchall()
    connection.close()

    return [row[0] for row in result]


def get_all_students():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT username
        FROM students
    """)

    result = cursor.fetchall()
    connection.close()

    return [row[0] for row in result]


def get_all_connections():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT student1, student2
        FROM connections
    """)

    result = cursor.fetchall()
    connection.close()

    return result


# =========================================================
# POSTS
# =========================================================

def add_post(username, content, image_path=None):
    if not content.strip() and not image_path:
        return False

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO posts
        (username, content, created_at, image_path)
        VALUES (?, ?, ?, ?)
    """, (
        username,
        content,
        datetime.now().isoformat(timespec="seconds"),
        image_path
    ))

    connection.commit()
    connection.close()

    return True


def get_all_posts():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT post_id, username, content, created_at, image_path
        FROM posts
        ORDER BY created_at DESC
    """)

    posts = cursor.fetchall()
    connection.close()

    return posts


def delete_post(post_id, username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM posts
        WHERE post_id = ? AND username = ?
    """, (post_id, username))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


# =========================================================
# LIKES
# =========================================================

def toggle_post_like(post_id, username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT 1 FROM post_likes
        WHERE post_id = ? AND username = ?
    """, (post_id, username))

    liked = cursor.fetchone() is not None

    if liked:
        cursor.execute("""
            DELETE FROM post_likes
            WHERE post_id = ? AND username = ?
        """, (post_id, username))

        connection.commit()
        connection.close()
        return False

    cursor.execute("""
        INSERT OR IGNORE INTO post_likes
        (post_id, username, created_at)
        VALUES (?, ?, ?)
    """, (
        post_id,
        username,
        datetime.now().isoformat(timespec="seconds")
    ))

    connection.commit()
    connection.close()

    return True


def get_post_like_count(post_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM post_likes
        WHERE post_id = ?
    """, (post_id,))

    count = cursor.fetchone()[0]
    connection.close()

    return count


def user_liked_post(post_id, username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT 1
        FROM post_likes
        WHERE post_id = ? AND username = ?
    """, (post_id, username))

    result = cursor.fetchone() is not None
    connection.close()

    return result


# =========================================================
# COMMENTS
# =========================================================

def add_comment(post_id, username, comment_text):
    comment_text = (comment_text or "").strip()

    if not comment_text:
        return False

    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO post_comments
        (post_id, username, comment_text, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        post_id,
        username,
        comment_text,
        datetime.now().isoformat(timespec="seconds")
    ))

    connection.commit()
    connection.close()

    return True


def get_post_comments(post_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT comment_id, username, comment_text, created_at
        FROM post_comments
        WHERE post_id = ?
        ORDER BY created_at ASC, comment_id ASC
    """, (post_id,))

    comments = cursor.fetchall()
    connection.close()

    return comments


def delete_comment(comment_id, username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM post_comments
        WHERE comment_id = ? AND username = ?
    """, (comment_id, username))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


# =========================================================
# ADMIN STATISTICS AND MODERATION
# =========================================================

def get_admin_statistics():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM students")
    students = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM connections")
    connections = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM posts")
    posts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM post_likes")
    likes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM post_comments")
    comments = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM students
        WHERE verified = 1
    """)
    verified = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM verified_students
        WHERE registered_username IS NULL
    """)
    unused_records = cursor.fetchone()[0]

    connection.close()

    return {
        "students": students,
        "connections": connections,
        "posts": posts,
        "likes": likes,
        "comments": comments,
        "verified": verified,
        "unused_records": unused_records
    }


def get_all_students_details():
    connection = connect_db()
    cursor = connection.cursor()

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
        ORDER BY name COLLATE NOCASE
    """)

    students = cursor.fetchall()
    connection.close()

    return students


def get_all_posts_admin():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT post_id, username, content, created_at, image_path
        FROM posts
        ORDER BY created_at DESC
    """)

    posts = cursor.fetchall()
    connection.close()

    return posts


def delete_post_admin(post_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM posts
        WHERE post_id = ?
    """, (post_id,))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


def get_all_comments_admin():
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            comment_id,
            post_id,
            username,
            comment_text,
            created_at
        FROM post_comments
        ORDER BY created_at DESC
    """)

    comments = cursor.fetchall()
    connection.close()

    return comments


def delete_comment_admin(comment_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM post_comments
        WHERE comment_id = ?
    """, (comment_id,))

    deleted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return deleted


def delete_student_admin(username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT registration_number
        FROM students
        WHERE username = ?
    """, (username,))

    result = cursor.fetchone()

    if not result:
        connection.close()
        return False

    registration_number = result[0]

    cursor.execute("""
        DELETE FROM posts
        WHERE username = ?
    """, (username,))

    cursor.execute("""
        DELETE FROM post_likes
        WHERE username = ?
    """, (username,))

    cursor.execute("""
        DELETE FROM post_comments
        WHERE username = ?
    """, (username,))

    cursor.execute("""
        DELETE FROM pending_requests
        WHERE sender = ? OR receiver = ?
    """, (username, username))

    cursor.execute("""
        DELETE FROM connections
        WHERE student1 = ? OR student2 = ?
    """, (username, username))

    cursor.execute("""
        DELETE FROM students
        WHERE username = ?
    """, (username,))

    if registration_number:
        cursor.execute("""
            UPDATE verified_students
            SET registered_username = NULL
            WHERE registration_number = ?
            AND registered_username = ?
        """, (registration_number, username))

    connection.commit()
    connection.close()

    return True


# Initialize tables on import
create_tables()


if __name__ == "__main__":
    print("CampusConnect database initialized.")
    print("Database:", DB_PATH)
