"""SQLite persistence and database initialization."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from zoneinfo import ZoneInfo

MANILA = ZoneInfo('Asia/Manila')


def now():
    return datetime.now(MANILA)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 260_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, rounds)
    return f'pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or not 100_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


@contextmanager
def connect(path: str):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 10000')
    try:
        yield db
    finally:
        db.close()


def init_database(path: str, demo_password: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode = WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT UNIQUE,
                requester_name TEXT NOT NULL,
                document_type TEXT NOT NULL,
                category TEXT NOT NULL,
                requester_type TEXT NOT NULL DEFAULT 'Not specified' CHECK(requester_type IN ('Student', 'Alumni', 'Not specified')),
                claimed_at TEXT,
                claimed_by TEXT,
                approved_at TEXT,
                approved_by TEXT,
                submission_date TEXT NOT NULL,
                deadline TEXT NOT NULL,
                priority_score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Processing', 'Ready for Release', 'Processed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                processed_at TEXT,
                demo INTEGER NOT NULL DEFAULT 0,
                CHECK(deadline >= submission_date)
            );
            CREATE TABLE IF NOT EXISTS portal_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                account_type TEXT NOT NULL CHECK(account_type IN ('Student','Alumni')),
                student_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                email_verified_at TEXT
            );
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                portal_user_id INTEGER PRIMARY KEY REFERENCES portal_users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                last_sent_at TEXT NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 1,
                window_started_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
            CREATE INDEX IF NOT EXISTS idx_requests_created ON requests(created_at);
            CREATE TABLE IF NOT EXISTS request_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL REFERENCES requests(id),
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_request_events_request ON request_events(request_id);
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                request_public_id TEXT,
                created_at TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0
            );
        ''')
        # Non-destructive migration for older Railway/local SQLite databases.
        # Keep the four original status values intact. Pickup is recorded in
        # claimed_at/claimed_by, avoiding a destructive requests-table rebuild.
        columns = {row['name'] for row in db.execute('PRAGMA table_info(requests)')}
        if 'requester_type' not in columns:
            db.execute("ALTER TABLE requests ADD COLUMN requester_type TEXT NOT NULL DEFAULT 'Not specified' CHECK(requester_type IN ('Student','Alumni','Not specified'))")
        if 'claimed_at' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN claimed_at TEXT')
        if 'claimed_by' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN claimed_by TEXT')
        # Release approval must be explicit. Older Ready-for-Release rows
        # remain unapproved and cannot be claimed until registrar confirms.
        if 'approved_at' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN approved_at TEXT')
        if 'approved_by' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN approved_by TEXT')
        if 'student_number' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN student_number TEXT')
        if 'purpose' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN purpose TEXT')
        if 'portal_user_id' not in columns:
            db.execute('ALTER TABLE requests ADD COLUMN portal_user_id INTEGER REFERENCES portal_users(id)')
        # Preserve already registered v1.4 accounts (grandfathered as verified).
        # Newly registered accounts in v1.5 begin unverified.
        portal_columns = {row['name'] for row in db.execute('PRAGMA table_info(portal_users)')}
        if 'email_verified_at' not in portal_columns:
            db.execute('ALTER TABLE portal_users ADD COLUMN email_verified_at TEXT')
            db.execute('UPDATE portal_users SET email_verified_at=created_at WHERE email_verified_at IS NULL')
        db.execute('''CREATE TABLE IF NOT EXISTS email_verification_tokens (
            portal_user_id INTEGER PRIMARY KEY REFERENCES portal_users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            last_sent_at TEXT NOT NULL,
            sent_count INTEGER NOT NULL DEFAULT 1,
            window_started_at TEXT NOT NULL
        )''')
        for field, definition in (
            ('date_reason', 'TEXT'),
            ('decision_at', 'TEXT'), ('decision_by', 'TEXT'),
            ('declined_at', 'TEXT'), ('declined_reason', 'TEXT'),
            ('cancelled_at', 'TEXT'), ('cancelled_reason', 'TEXT'),
            ('pickup_at', 'TEXT'), ('pickup_note', 'TEXT')
        ):
            if field not in columns:
                db.execute(f'ALTER TABLE requests ADD COLUMN {field} {definition}')
        # One request can contain several different documents. Old rows are
        # migrated as single-item requests, without modifying their IDs.
        db.execute('''CREATE TABLE IF NOT EXISTS request_documents (
            request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
            document_type TEXT NOT NULL,
            PRIMARY KEY (request_id, document_type)
        )''')
        db.execute('''INSERT OR IGNORE INTO request_documents(request_id,document_type)
                      SELECT id,document_type FROM requests''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_requests_portal_user ON requests(portal_user_id)')
        existing = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if existing is None:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    'INSERT INTO users (username,display_name,password_hash,created_at) VALUES (?,?,?,?)',
                    ('admin', 'Registrar Administrator', hash_password(demo_password), now().isoformat())
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise


def attach_documents(db, records: list[dict]) -> list[dict]:
    docs: dict[int, list[str]] = {}
    for row in db.execute('SELECT request_id,document_type FROM request_documents ORDER BY rowid'):
        docs.setdefault(row['request_id'], []).append(row['document_type'])
    for item in records:
        item['documents'] = docs.get(item['id'], [item['document_type']])
    return records


def fetch_records(db) -> list[dict]:
    records = [dict(row) | {'arrival_number': row['id']}
               for row in db.execute('SELECT * FROM requests ORDER BY id')]
    return attach_documents(db, records)


def persist_scores(db, records: list[dict]):
    db.executemany(
        'UPDATE requests SET priority_score=? WHERE id=?',
        [(record['priority_score'], record['id']) for record in records if record['status'] == 'Pending' and not record.get('cancelled_at') and not record.get('declined_at')]
    )


def add_notification(db, title: str, message: str, public_id: str | None = None):
    db.execute(
        'INSERT INTO notifications (title,message,request_public_id,created_at) VALUES (?,?,?,?)',
        (title, message, public_id, now().isoformat())
    )


def add_event(db, request_pk: int, status: str, message: str):
    db.execute(
        'INSERT INTO request_events (request_id,status,message,created_at) VALUES (?,?,?,?)',
        (request_pk, status, message, now().isoformat())
    )


def insert_request(db, *, name: str, document_type: str, category: str, deadline: str,
                   submission_date: str, requester_type: str = 'Not specified', demo: bool = False,
                   student_number: str | None = None, purpose: str | None = None,
                   portal_user_id: int | None = None, documents: list[str] | None = None,
                   date_reason: str | None = None) -> dict:
    from .algorithms import calculate_score
    from datetime import date
    if requester_type not in ('Student', 'Alumni', 'Not specified'):
        raise ValueError('Invalid requester type')
    timestamp = now().isoformat()
    preview = {'submission_date': submission_date, 'deadline': deadline, 'category': category}
    score = calculate_score(preview, date.fromisoformat(submission_date))
    cursor = db.execute('''
        INSERT INTO requests (requester_name,document_type,category,requester_type,submission_date,
                              deadline,priority_score,created_at,updated_at,demo,student_number,purpose,portal_user_id,date_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (name, document_type, category, requester_type, submission_date, deadline, score,
          timestamp, timestamp, int(demo),student_number,purpose,portal_user_id,date_reason))
    pk = cursor.lastrowid
    public_id = f'REQ-{pk:04d}'
    db.execute('UPDATE requests SET public_id=? WHERE id=?', (public_id, pk))
    for doc in (documents or [document_type]):
        db.execute('INSERT INTO request_documents(request_id,document_type) VALUES (?,?)', (pk, doc))
    add_event(db, pk, 'Pending', 'Request submitted successfully')
    return {'id': public_id, 'score': round(score, 2), 'status': 'Pending'}


def get_secret(path: str) -> str:
    explicit = os.environ.get('QUEUEWISE_SECRET_KEY')
    if explicit:
        return explicit
    file = Path(path).parent / '.session_secret'
    file.parent.mkdir(parents=True, exist_ok=True)
    if file.exists():
        return file.read_text().strip()
    secret = secrets.token_hex(32)
    try:
        fd = os.open(str(file), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(secret)
    except FileExistsError:
        return file.read_text().strip()
    return secret
