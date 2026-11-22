"""QueueWise API, PWA delivery, and staff-only registrar operations."""
from __future__ import annotations

from datetime import date, datetime, timedelta, datetime, timezone
import hmac
import hashlib
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from .algorithms import CATEGORIES, DOCUMENT_TYPES, QueueEngine
from .mailer import EmailDeliveryError, sender_configured, send_verification_email
from .storage import (connect, init_database, get_secret, now, verify_password, attach_documents, MANILA,
                      hash_password, fetch_records, persist_scores,
                      insert_request, add_notification, add_event)

LOGGER = logging.getLogger('queuewise')
ROOT = Path(__file__).resolve().parent
PUBLIC_ID_RE = re.compile(r'^REQ-\d{4,}$')
WORD_RE = re.compile(r"^[^\W\d_]+(?:['.\-][^\W\d_]+)*$", flags=re.UNICODE)
# Supports names like Mary Jane, Dela Cruz, O'Neil, and a middle initial M.
NAME_PART_WORD_RE = re.compile(r"^[^\W\d_]+(?:[.'’\-][^\W\d_]+)*\.?$", flags=re.UNICODE)
STUDENT_NUMBER_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{4,23}$')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{32,128}$')
VERIFY_TTL = timedelta(hours=24)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_SENDS_PER_DAY = 5
ALLOWED_TRANSITIONS = {
    'Pending': {'Processing', 'Processed'},
    'Processing': {'Processed'},
    'Ready for Release': set(),
    # Processed is not synonymous with approved for release.
    'Processed': set(),
}


class LoginPayload(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=256)


class NewRequest(BaseModel):
    requester_name: str = Field(max_length=200)
    # Optional for backwards-compatible API clients. New UI requires a selection.
    requester_type: Literal['Student', 'Alumni'] | None = None
    student_number: str | None = Field(default=None, max_length=40)
    purpose: str | None = Field(default=None, max_length=240)
    document_type: str
    document_types: list[str] | None = None
    category: str
    deadline: str
    date_reason: str | None = Field(default=None, max_length=500)


class RegisterPayload(BaseModel):
    # New registration UI uses separate name fields.  Legacy full_name is
    # accepted for backwards compatibility with older API clients.
    first_name: str | None = Field(default=None, max_length=60)
    middle_name: str | None = Field(default=None, max_length=60)
    last_name: str | None = Field(default=None, max_length=60)
    full_name: str | None = Field(default=None, max_length=200)
    account_type: Literal['Student', 'Alumni']
    student_number: str = Field(max_length=40)
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


class VerificationPayload(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class ResendVerificationPayload(BaseModel):
    email: str = Field(max_length=254)


class RequesterLoginPayload(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    account_type: Literal['Student', 'Alumni'] | None = None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class ChangeStatus(BaseModel):
    status: Literal['Processing', 'Ready for Release', 'Processed']


class DecisionPayload(BaseModel):
    decision: Literal['approve', 'decline']
    reason: str | None = Field(default=None, max_length=500)


class PickupSchedulePayload(BaseModel):
    pickup_at: str
    note: str | None = Field(default=None, max_length=500)


class CancelPayload(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class SeedDemo(BaseModel):
    count: int = Field(default=12, ge=1, le=150)


def fail(status_code: int, message: str):
    raise HTTPException(status_code=status_code, detail=message)


def require_csrf(request: Request):
    token = request.session.get('csrf')
    received = request.headers.get('x-csrf-token', '')
    if not token or not hmac.compare_digest(token, received):
        fail(403, 'Security token expired. Refresh the page and try again.')


def require_requester(request: Request):
    user_id = request.session.get('portal_user_id')
    if not isinstance(user_id, int):
        fail(401, 'Student or alumni login required.')
    with connect(request.app.state.db_path) as db:
        user = db.execute('SELECT id,full_name,account_type,student_number,email,email_verified_at FROM portal_users WHERE id=?', (user_id,)).fetchone()
    if user is None or not user['email_verified_at']:
        fail(401, 'Session expired or email unverified. Please sign in after verification.')
    return dict(user)


def validated_student_number(value: str) -> str:
    number = value.strip().upper()
    if not STUDENT_NUMBER_RE.fullmatch(number):
        fail(400, 'Student number must contain 5–24 letters, digits, or hyphens (no spaces).')
    return number


def validated_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        fail(400, 'Enter a valid email address.')
    return email


def validated_password(value: str):
    if not (10 <= len(value) <= 128 and re.search(r'[a-z]', value)
            and re.search(r'[A-Z]', value) and re.search(r'\d', value)
            and re.search(r'[^A-Za-z0-9]', value)):
        fail(400, 'Password must have 10+ characters, uppercase, lowercase, a number, and a symbol.')


def public_user(user):
    return {'id': user['id'], 'role': user['account_type'],
            'display_name': user['full_name'], 'email': user['email'],
            'student_number': user['student_number']}


def require_staff(request: Request):
    user_id = request.session.get('staff_id')
    if not isinstance(user_id, int):
        fail(401, 'Registrar login required.')
    with connect(request.app.state.db_path) as db:
        user = db.execute('SELECT id,username,display_name FROM users WHERE id=?', (user_id,)).fetchone()
    if user is None:
        fail(401, 'Session expired. Please sign in again.')
    return dict(user)


def normalize_name(value: str) -> str:
    """Validate full display name, including optional middle initial or surname particles.

    Name must still have a complete first and last part; a lone last initial
    is not accepted. Used for legacy API clients and request submissions.
    """
    name = ' '.join(value.strip().split())
    words = name.split(' ')
    if not (2 <= len(name) <= 200 and len(words) >= 2
            and all(NAME_PART_WORD_RE.fullmatch(word) for word in words)
            and sum(ch.isalpha() for ch in words[0]) >= 2
            and sum(ch.isalpha() for ch in words[-1]) >= 2):
        fail(400, 'Enter a complete first and last name using letters (middle initials are allowed).')
    return name


def validated_name_part(value: str | None, label: str, *, required: bool = False) -> str | None:
    """Validate a single registration name component, preserving user casing."""
    text = ' '.join((value or '').split())
    if not text:
        if required:
            fail(400, f'{label} is required.')
        return None
    if len(text) > 60 or not all(NAME_PART_WORD_RE.fullmatch(word) for word in text.split()):
        fail(400, f'{label} must contain valid letters only (hyphens, apostrophes, and periods are allowed).')
    letter_count = sum(character.isalpha() for character in text)
    if letter_count < (2 if required else 1):
        fail(400, f'{label} must contain at least {2 if required else 1} letter(s).')
    return text


def normalize_registration_name(payload: RegisterPayload) -> tuple[str, str | None, str | None, str | None]:
    """Assemble name without making middle name mandatory; preserve legacy API."""
    if any(value is not None for value in (payload.first_name, payload.middle_name, payload.last_name)):
        first = validated_name_part(payload.first_name, 'First name', required=True)
        middle = validated_name_part(payload.middle_name, 'Middle name')
        last = validated_name_part(payload.last_name, 'Last name', required=True)
        full = ' '.join(part for part in (first, middle, last) if part)
        if len(full) > 200:
            fail(400, 'The complete name is too long.')
        return full, first, middle, last
    if payload.full_name is not None:
        return normalize_name(payload.full_name), None, None, None
    fail(400, 'First name and last name are required.')


def validate_new_request(item: NewRequest):
    name = normalize_name(item.requester_name)
    if item.document_type not in DOCUMENT_TYPES:
        fail(400, 'Please select a valid document type.')
    if item.category not in CATEGORIES:
        fail(400, 'Please select a valid requester category.')
    try:
        deadline = date.fromisoformat(item.deadline)
    except (TypeError, ValueError):
        fail(400, 'Please provide a valid deadline (YYYY-MM-DD).')
    today = now().date()
    if deadline < today:
        fail(400, 'Deadline cannot be earlier than today.')
    if deadline > today + timedelta(days=365 * 3):
        fail(400, 'Deadline must be within the next three years.')
    return name, deadline.isoformat(), today.isoformat()


def ensure_id(value: str):
    if not PUBLIC_ID_RE.fullmatch(value):
        fail(400, 'Invalid request ID. Example: REQ-0001.')
    return value


def display_request_status(record: dict) -> str:
    """Never disclose release readiness before explicit registrar approval."""
    if record.get('cancelled_at'):
        return 'Cancelled'
    if record.get('declined_at'):
        return 'Declined'
    if record.get('claimed_at'):
        return 'Claimed'
    if record.get('pickup_at') and record.get('approved_at') and datetime.fromisoformat(record['pickup_at']) > now():
        return 'Pickup Scheduled'
    if record.get('status') == 'Ready for Release' and not record.get('approved_at'):
        return 'Awaiting Approval'
    if record.get('status') == 'Processed' and not record.get('approved_at'):
        return 'Awaiting Approval'
    return record['status']


def read_staff_snapshot(db) -> dict:
    """Refresh on every priority-sensitive view; the heap is a separate ADT."""
    records = fetch_records(db)
    engine = QueueEngine(records)
    engine.refresh(now().date())
    persist_scores(db, records)
    ranked = engine.ranked()
    all_records = sorted(records, key=lambda rec: rec['arrival_number'], reverse=True)
    active_records = [r for r in records if not r.get('cancelled_at') and not r.get('declined_at')]
    counts = {status: sum(r['status'] == status for r in active_records)
              for status in ALLOWED_TRANSITIONS}
    claimed = sorted((r for r in records if r.get('claimed_at')),
                     key=lambda r: (r['claimed_at'], r['id']), reverse=True)
    return {
        'requests': all_records,
        'claimed': claimed,
        'priority': ranked,
        'arrivals': engine.arrivals.traverse(),
        'next_id': engine.heap.peek(),
        'stats': {
            'total': len(records),
            'pending': len(engine.heap.items),
            'declined': sum(bool(r.get('declined_at')) for r in records),
            'cancelled': sum(bool(r.get('cancelled_at')) for r in records),
            'processing': counts['Processing'],
            'ready': sum(r['status'] == 'Ready for Release' and r.get('approved_at') and not r.get('claimed_at') and (not r.get('pickup_at') or datetime.fromisoformat(r['pickup_at']) <= now()) for r in active_records),
            'awaiting_approval': sum(
                (r['status'] == 'Processed' or r['status'] == 'Ready for Release')
                and not r.get('approved_at') and not r.get('claimed_at')
                for r in records
            ),
            'processed': counts['Processed'] - len(claimed),
            'claimed': len(claimed),
            'ready_to_claim': sum(r['status'] == 'Ready for Release' and r.get('approved_at') and not r.get('claimed_at') and (not r.get('pickup_at') or datetime.fromisoformat(r['pickup_at']) <= now()) for r in active_records),
            'students': sum(r.get('requester_type') == 'Student' for r in records),
            'alumni': sum(r.get('requester_type') == 'Alumni' for r in records),
            'unclassified': sum(r.get('requester_type') not in ('Student', 'Alumni') for r in records),
            'hash_buckets': engine.hash_table.capacity,
            'hash_entries': engine.hash_table.size,
            'heap_entries': len(engine.heap.items),
            'heap_valid': engine.heap.valid(),
        },
        'refreshed_at': now().isoformat(),
    }


def create_app(db_path: str | None = None, testing: bool = False) -> FastAPI:
    database = str(Path(db_path) if db_path else Path(os.environ.get('QUEUEWISE_DB_PATH') or (ROOT.parent / 'instance' / 'queuewise.db')))
    secret = get_secret(database)
    demo_password = os.environ.get('QUEUEWISE_ADMIN_PASSWORD', 'CvSU@2026Demo!')
    init_database(database, demo_password)
    app = FastAPI(title='QueueWise', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = database
    app.state.testing = testing
    app.state.email_outbox = []
    app.add_middleware(
        SessionMiddleware, secret_key=secret, session_cookie='queuewise_session',
        max_age=8 * 3600, same_site='lax',
        https_only=(os.environ.get('QUEUEWISE_HTTPS') == '1')
    )
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; manifest-src 'self'"
        )
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(HTTPException)
    async def known_error(request: Request, exc: HTTPException):
        return JSONResponse({'error': str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({'error': 'One or more fields are missing or invalid. Please check your input.'}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        LOGGER.exception('Unexpected QueueWise error: %s', request.url.path)
        return JSONResponse({'error': 'An unexpected error occurred. Please retry.'}, status_code=500)

    @app.get('/', include_in_schema=False)
    def index():
        return HTMLResponse((ROOT / 'templates' / 'index.html').read_text('utf-8'), headers={'Cache-Control': 'no-cache'})

    @app.get('/manifest.webmanifest', include_in_schema=False)
    def manifest():
        return FileResponse(ROOT / 'static' / 'manifest.webmanifest', media_type='application/manifest+json')

    @app.get('/sw.js', include_in_schema=False)
    def service_worker():
        return FileResponse(ROOT / 'static' / 'js' / 'sw.js', media_type='text/javascript', headers={'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/'})

    @app.get('/offline', include_in_schema=False)
    def offline():
        return HTMLResponse((ROOT / 'templates' / 'offline.html').read_text('utf-8'))

    @app.get('/api/bootstrap')
    def bootstrap(request: Request):
        if 'csrf' not in request.session:
            request.session['csrf'] = secrets.token_urlsafe(32)
        user = None
        if isinstance(request.session.get('staff_id'), int):
            with connect(database) as db:
                record = db.execute('SELECT id,username,display_name FROM users WHERE id=?',
                                    (request.session['staff_id'],)).fetchone()
                if record:
                    user = dict(record) | {'role': 'Registrar'}
                else:
                    request.session.pop('staff_id', None)
        elif isinstance(request.session.get('portal_user_id'), int):
            with connect(database) as db:
                record = db.execute(
                    'SELECT id,full_name,account_type,student_number,email,email_verified_at FROM portal_users WHERE id=?',
                    (request.session['portal_user_id'],)
                ).fetchone()
                if record and record['email_verified_at']:
                    user = public_user(record)
                else:
                    request.session.pop('portal_user_id', None)
        return {
            'csrf_token': request.session['csrf'], 'user': user,
            'today': now().date().isoformat(),
            'documents': DOCUMENT_TYPES, 'categories': list(CATEGORIES),
            'demo': True,
            'requester_types': ['Student', 'Alumni'],
        }

    @app.post('/api/auth/login', dependencies=[Depends(require_csrf)])
    def login(payload: LoginPayload, request: Request):
        username = payload.username.strip().lower()
        with connect(database) as db:
            user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user is None or not verify_password(payload.password, user['password_hash']):
            fail(401, 'Incorrect username or password.')
        request.session.clear()
        request.session['staff_id'] = user['id']
        request.session['csrf'] = secrets.token_urlsafe(32)
        return {'message': 'Signed in successfully.', 'csrf_token': request.session['csrf'],
                'user': {'id': user['id'], 'username': user['username'], 'display_name': user['display_name'], 'role': 'Registrar'}}

    @app.post('/api/auth/register', status_code=201, dependencies=[Depends(require_csrf)])
    def register_requester(payload: RegisterPayload, request: Request):
        # Never silently create an account that cannot receive an activation email.
        if not sender_configured(testing):
            fail(503, 'Email verification is not configured. Ask the administrator to set Gmail API credentials and the public URL in Railway.')
        name, first_name, middle_name, last_name = normalize_registration_name(payload)
        number = validated_student_number(payload.student_number)
        email = validated_email(payload.email)
        validated_password(payload.password)
        if payload.password != payload.confirm_password:
            fail(400, 'Passwords do not match.')
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
        stamp = datetime.now(timezone.utc)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT id FROM portal_users WHERE email=? OR student_number=?',
                              (email, number)).fetchone():
                    fail(409, 'This email or student number is already registered. Please sign in or request a verification email.')
                cursor = db.execute("""INSERT INTO portal_users
                    (full_name,first_name,middle_name,last_name,account_type,student_number,email,password_hash,created_at,email_verified_at)
                    VALUES (?,?,?,?,?,?,?,?,?,NULL)""",
                    (name,first_name,middle_name,last_name,payload.account_type,number,email,hash_password(payload.password),now().isoformat()))
                user_id = cursor.lastrowid
                db.execute("""INSERT INTO email_verification_tokens
                    (portal_user_id,token_hash,expires_at,last_sent_at,sent_count,window_started_at)
                    VALUES (?,?,?,?,1,?)""",
                    (user_id,digest,(stamp+VERIFY_TTL).isoformat(),stamp.isoformat(),stamp.isoformat()))
                db.execute('COMMIT')
            except sqlite3.IntegrityError:
                db.execute('ROLLBACK')
                fail(409, 'This email or student number is already registered. Please sign in or request a verification email.')
            except Exception:
                db.execute('ROLLBACK')
                raise
        # Sending occurs after committing SQLite, to avoid holding a write lock
        # during outbound network I/O. Failure does not activate the account.
        try:
            send_verification_email(email, name, token, testing=testing, outbox=app.state.email_outbox)
        except EmailDeliveryError as exc:
            # Allow an immediate retry if delivery failed; tell the user explicitly.
            with connect(database) as db:
                db.execute('DELETE FROM email_verification_tokens WHERE portal_user_id=?', (user_id,))
            fail(503, f'Account saved but no verification email was sent. {exc} Use the resend verification option after checking email settings.')
        return {'message': 'Registration received. Check your inbox to verify your email before signing in.',
                'requires_verification': True,
                'user': {'role': payload.account_type, 'email': email, 'student_number': number}}

    @app.post('/api/auth/verify-email', dependencies=[Depends(require_csrf)])
    def verify_email(payload: VerificationPayload):
        if not TOKEN_RE.fullmatch(payload.token):
            fail(400, 'Invalid verification link. Request another email.')
        digest = hashlib.sha256(payload.token.encode('utf-8')).hexdigest()
        stamp = datetime.now(timezone.utc)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute("""SELECT t.portal_user_id,t.expires_at,p.email_verified_at
                    FROM email_verification_tokens t
                    JOIN portal_users p ON p.id=t.portal_user_id
                    WHERE t.token_hash=?""", (digest,)).fetchone()
                if not record:
                    fail(400, 'Verification link is invalid or already used. Request a new one.')
                if datetime.fromisoformat(record['expires_at']) <= stamp:
                    fail(400, 'Verification link expired. Request a new verification email.')
                if record['email_verified_at'] is not None:
                    fail(400, 'This email address is already verified. Please sign in.')
                db.execute('UPDATE portal_users SET email_verified_at=? WHERE id=?',
                           (stamp.isoformat(), record['portal_user_id']))
                db.execute('DELETE FROM email_verification_tokens WHERE portal_user_id=?',
                           (record['portal_user_id'],))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': 'Email verified successfully. You can now sign in.'}

    @app.post('/api/auth/resend-verification', dependencies=[Depends(require_csrf)])
    def resend_verification(payload: ResendVerificationPayload):
        if not sender_configured(testing):
            fail(503, 'Verification email is not configured. Contact the administrator.')
        email = validated_email(payload.email)
        stamp = datetime.now(timezone.utc)
        generic = {'message': 'If this account is awaiting verification, a new email will be sent. Check Inbox and Spam.'}
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                user = db.execute('SELECT id,full_name,email_verified_at FROM portal_users WHERE email=?',
                                  (email,)).fetchone()
                if not user or user['email_verified_at']:
                    db.execute('COMMIT')
                    return generic
                existing = db.execute('SELECT last_sent_at,sent_count,window_started_at FROM email_verification_tokens WHERE portal_user_id=?',
                                      (user['id'],)).fetchone()
                if existing:
                    last = datetime.fromisoformat(existing['last_sent_at'])
                    if stamp-last < RESEND_COOLDOWN:
                        fail(429, 'Please wait 60 seconds before requesting another email.')
                    window_start = datetime.fromisoformat(existing['window_started_at'])
                    count = existing['sent_count'] if stamp-window_start < timedelta(days=1) else 0
                    if count >= MAX_SENDS_PER_DAY:
                        fail(429, 'Email resend limit reached. Please try again tomorrow.')
                    window = window_start if stamp-window_start < timedelta(days=1) else stamp
                else:
                    count, window = 0, stamp
                token = secrets.token_urlsafe(32)
                digest = hashlib.sha256(token.encode()).hexdigest()
                db.execute("""INSERT INTO email_verification_tokens
                    (portal_user_id,token_hash,expires_at,last_sent_at,sent_count,window_started_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(portal_user_id) DO UPDATE SET
                    token_hash=excluded.token_hash, expires_at=excluded.expires_at,
                    last_sent_at=excluded.last_sent_at, sent_count=excluded.sent_count,
                    window_started_at=excluded.window_started_at""",
                    (user['id'],digest,(stamp+VERIFY_TTL).isoformat(),stamp.isoformat(),count+1,window.isoformat()))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        try:
            send_verification_email(email,user['full_name'],token,testing=testing,outbox=app.state.email_outbox)
        except EmailDeliveryError as exc:
            # Remove the unsent token; resend can be retried immediately.
            with connect(database) as db:
                db.execute('DELETE FROM email_verification_tokens WHERE portal_user_id=? AND token_hash=?',
                           (user['id'],digest))
            fail(503, str(exc))
        return generic

    @app.post('/api/auth/requester-login', dependencies=[Depends(require_csrf)])
    def requester_login(payload: RequesterLoginPayload, request: Request):
        email = validated_email(payload.email)
        with connect(database) as db:
            user = db.execute('SELECT * FROM portal_users WHERE email=?', (email,)).fetchone()
        if user is None or not verify_password(payload.password, user['password_hash']):
            fail(401, 'Incorrect email or password.')
        if not user['email_verified_at']:
            fail(403, 'Email not verified. Open the verification email, or request a new link.')
        if payload.account_type and payload.account_type != user['account_type']:
            fail(403, f'This account belongs to the {user["account_type"]} Portal. Select the correct sign-in tab.')
        request.session.clear()
        request.session['portal_user_id'] = user['id']
        request.session['csrf'] = secrets.token_urlsafe(32)
        return {'message': 'Signed in successfully.', 'csrf_token': request.session['csrf'],
                'user': public_user(user)}

    @app.get('/api/my/requests')
    def my_requests(user=Depends(require_requester)):
        with connect(database) as db:
            items = [dict(row) for row in db.execute("""SELECT id,public_id,document_type,category,purpose,deadline,date_reason,
                    priority_score,status,submission_date,updated_at,processed_at,claimed_at,approved_at,
                    decision_at,declined_at,declined_reason,cancelled_at,cancelled_reason,pickup_at,pickup_note
                    FROM requests WHERE portal_user_id=? ORDER BY id DESC""", (user['id'],))]
            attach_documents(db, items)
        for item in items:
            item['status'] = display_request_status(item)
            item['approved_for_release'] = bool(item.get('approved_at'))
        return {'requests': items}

    @app.get('/api/my/notifications')
    def my_notifications(user=Depends(require_requester)):
        with connect(database) as db:
            events = [dict(row) for row in db.execute("""SELECT r.public_id,r.approved_at,e.status,e.message,e.created_at
                 FROM request_events e JOIN requests r ON r.id=e.request_id
                 WHERE r.portal_user_id=? ORDER BY e.id DESC LIMIT 100""", (user['id'],))]
        for event in events:
            if event['status'] == 'Ready for Release' and not event['approved_at']:
                event['status'] = 'Awaiting Approval'
                event['message'] = 'Waiting for registrar release approval.'
            event.pop('approved_at', None)
        return {'notifications': events}

    @app.post('/api/auth/logout', dependencies=[Depends(require_csrf)])
    def logout(request: Request):
        request.session.clear()
        request.session['csrf'] = secrets.token_urlsafe(32)
        return {'message': 'Signed out.', 'csrf_token': request.session['csrf']}

    @app.post('/api/requests', status_code=201, dependencies=[Depends(require_csrf)])
    def submit_request(payload: NewRequest, request: Request):
        # Preserve the legacy guest demo API; registered requesters are always
        # identified by their server-side account rather than client form fields.
        registered = None
        if isinstance(request.session.get('portal_user_id'), int):
            registered = require_requester(request)
        if not registered and not testing:
            fail(401, 'Create a Student or Alumni account, verify your email, and sign in before submitting a document request.')
        if registered:
            payload = payload.model_copy(update={
                'requester_name': registered['full_name'],
                'requester_type': registered['account_type'],
                'student_number': registered['student_number']
            })
            if not (payload.purpose or '').strip():
                fail(400, 'Please enter the purpose of your document request.')
        documents = payload.document_types if payload.document_types is not None else [payload.document_type]
        if not isinstance(documents, list) or not 1 <= len(documents) <= 5:
            fail(400, 'Select between one and five documents.')
        if any(not isinstance(doc, str) or doc not in DOCUMENT_TYPES for doc in documents):
            fail(400, 'One or more selected document types are invalid.')
        if len(set(documents)) != len(documents) or documents[0] != payload.document_type:
            fail(400, 'Document selections must be unique and match the primary document.')
        date_reason = ' '.join((payload.date_reason or '').split())
        if registered and not 10 <= len(date_reason) <= 500:
            fail(400, 'Explain why you need the documents on that date (10–500 characters).')
        if date_reason and not 10 <= len(date_reason) <= 500:
            fail(400, 'Date Needed reason must be 10–500 characters.')
        name, deadline, submitted = validate_new_request(payload)
        student_number = validated_student_number(payload.student_number) if payload.student_number else None
        purpose = ' '.join(payload.purpose.split()) if payload.purpose else None
        if purpose is not None and not 6 <= len(purpose) <= 180:
            fail(400, 'Purpose must contain between 6 and 180 characters.')
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                engine = QueueEngine(fetch_records(db))
                result = insert_request(db, name=name, document_type=payload.document_type,
                                        category=payload.category, deadline=deadline,
                                        submission_date=submitted, requester_type=payload.requester_type or 'Not specified',
                                        student_number=student_number, purpose=purpose,
                                        portal_user_id=registered['id'] if registered else None,
                                        documents=documents, date_reason=date_reason or None)
                inserted = db.execute('SELECT * FROM requests WHERE public_id=?', (result['id'],)).fetchone()
                engine.add_record(dict(inserted) | {'arrival_number': inserted['id']})
                if not engine.heap.valid():
                    raise RuntimeError('Heap invariant not satisfied after insertion')
                add_notification(db, 'New document request', f'{result["id"]} has entered the queue.', result['id'])
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'request': result, 'message': 'Request submitted and queued successfully.'}

    @app.get('/api/track/{public_id}')
    def track(public_id: str):
        ensure_id(public_id)
        with connect(database) as db:
            # Demonstrate ID lookup through the custom separate-chaining hash table.
            engine = QueueEngine(fetch_records(db))
            record = engine.hash_table.get(public_id)
            if record is None:
                fail(404, 'No request was found with that ID.')
            # ID-only public tracking intentionally hides reasons, document
            # names, pickup instructions, and appointment details. A verified
            # account can see its own detailed history via /api/my/*.
            public_messages = {
                'Pending': 'Request received.',
                'Processing': 'Request processing started.',
                'Processed': 'Document preparation updated.',
                'Approved': 'Registrar accepted request for preparation.',
                'Ready for Release': 'The registrar updated release readiness.',
                'Claimed': 'Collection confirmed.',
                'Declined': 'Request declined. Sign in for the explanation.',
                'Cancelled': 'Request cancelled.',
            }
            events = [
                {'status': ('Awaiting Approval' if row['status']=='Ready for Release' and not record.get('approved_at')
                            else row['status']),
                 'message': public_messages.get(row['status'], 'Request status updated.'),
                 'created_at': row['created_at']}
                for row in db.execute('SELECT status,created_at FROM request_events WHERE request_id=? ORDER BY id',
                                      (record['id'],))
            ]
        return {'request': {'id': record['public_id'],
                            'status': display_request_status(record),
                            'approved_for_release': bool(record.get('approved_at')),
                            'submitted_at': record['submission_date'], 'updated_at': record['updated_at'],
                            'processed_at': record['processed_at'], 'claimed_at': record.get('claimed_at')},
                'events': events}

    @app.get('/api/admin/requests')
    def get_requests(request: Request, user=Depends(require_staff)):
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                data = read_staff_snapshot(db)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return data

    @app.post('/api/admin/process-next', dependencies=[Depends(require_csrf)])
    def process_next(request: Request, user=Depends(require_staff)):
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                engine = QueueEngine(fetch_records(db))
                if engine.heap.is_empty():
                    fail(409, 'The pending queue is empty. No request to process.')
                engine.refresh(now().date())
                persist_scores(db, engine.records)
                chosen = engine.process_next()
                timestamp = now().isoformat()
                result = db.execute('''UPDATE requests SET status=?,processed_at=?,updated_at=?
                    WHERE id=? AND status='Pending' AND declined_at IS NULL AND cancelled_at IS NULL''',
                    ('Processed', timestamp, timestamp, chosen['id']))
                if result.rowcount != 1:
                    fail(409, 'Request changed while processing. Refresh and retry.')
                add_event(db, chosen['id'], 'Awaiting Approval', 'Registrar processed the request; release requires administrator approval')
                add_notification(db, 'Awaiting approval', f'{chosen["public_id"]} was processed; release approval is still required.', chosen['public_id'])
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{chosen["public_id"]} was processed and is awaiting registrar approval.', 'request_id': chosen['public_id']}

    @app.patch('/api/admin/requests/{public_id}/status', dependencies=[Depends(require_csrf)])
    def update_status(public_id: str, payload: ChangeStatus, request: Request, user=Depends(require_staff)):
        ensure_id(public_id)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT * FROM requests WHERE public_id=?', (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
                if record['claimed_at'] is not None or record['cancelled_at'] or record['declined_at']:
                    fail(409, 'Claimed, cancelled, or declined requests cannot be modified.')
                if payload.status == 'Ready for Release':
                    fail(409, 'Release requires explicit approval. Use Approve for Release instead.')
                if payload.status not in ALLOWED_TRANSITIONS[record['status']]:
                    fail(409, f'Cannot change status from {record["status"]} to {payload.status}.')
                timestamp = now().isoformat()
                processed = timestamp if payload.status == 'Processed' else record['processed_at']
                db.execute('UPDATE requests SET status=?,processed_at=?,updated_at=? WHERE id=?',
                           (payload.status, processed, timestamp, record['id']))
                add_event(db, record['id'], payload.status, f'Registrar updated the status to {payload.status}')
                add_notification(db, 'Status updated', f'{public_id} is now {payload.status}.', public_id)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{public_id} updated to {payload.status}.'}

    @app.post('/api/my/requests/{public_id}/cancel', dependencies=[Depends(require_csrf)])
    def cancel_request(public_id: str, payload: CancelPayload, request: Request,
                       user=Depends(require_requester)):
        ensure_id(public_id)
        reason = ' '.join((payload.reason or '').split())
        if reason and len(reason) < 5:
            fail(400, 'Cancellation explanation must be at least five characters when provided.')
        timestamp = now().isoformat()
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT * FROM requests WHERE public_id=? AND portal_user_id=?',
                                    (public_id, user['id'])).fetchone()
                if record is None:
                    fail(404, 'Request not found in your account.')
                if record['cancelled_at'] or record['declined_at'] or record['claimed_at']:
                    fail(409, 'This request is already closed.')
                if record['approved_at'] or record['pickup_at']:
                    fail(409, 'This request is already scheduled for release. Contact the registrar for help.')
                db.execute('UPDATE requests SET cancelled_at=?,cancelled_reason=?,updated_at=? WHERE id=?',
                           (timestamp, reason or 'Cancelled by requester', timestamp, record['id']))
                add_event(db, record['id'], 'Cancelled', f'Requester cancelled the request: {reason or "No reason provided"}')
                add_notification(db, 'Request cancelled', f'{public_id} was cancelled by its requester.', public_id)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{public_id} cancelled. You may submit a corrected new request.'}

    @app.post('/api/admin/requests/{public_id}/decision', dependencies=[Depends(require_csrf)])
    def decide_request(public_id: str, payload: DecisionPayload, request: Request,
                       user=Depends(require_staff)):
        ensure_id(public_id)
        reason = ' '.join((payload.reason or '').split())
        if payload.decision == 'decline' and not 10 <= len(reason) <= 500:
            fail(400, 'Provide a decline reason (10–500 characters) so the requester understands why.')
        timestamp = now().isoformat()
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT * FROM requests WHERE public_id=?', (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
                if record['claimed_at'] or record['cancelled_at'] or record['declined_at'] or record['approved_at']:
                    fail(409, 'This request has already been closed or scheduled.')
                if record['decision_at']:
                    fail(409, 'Request has already been approved. It cannot be decided again.')
                if payload.decision == 'decline':
                    db.execute('UPDATE requests SET declined_at=?,declined_reason=?,updated_at=? WHERE id=?',
                               (timestamp, reason, timestamp, record['id']))
                    add_event(db, record['id'], 'Declined', f'Registrar declined the request. Reason: {reason}')
                    add_notification(db, 'Request declined', f'{public_id} declined: {reason}', public_id)
                    message = f'{public_id} declined. The requester can see your reason.'
                else:
                    # Approval of the request is separate from pickup scheduling.
                    # Existing status values remain compatible with old SQLite DBs.
                    db.execute('UPDATE requests SET decision_at=?,decision_by=?,status=?,updated_at=? WHERE id=?',
                               (timestamp, user['username'], 'Processing' if record['status']=='Pending' else record['status'], timestamp, record['id']))
                    add_event(db, record['id'], 'Approved', 'Registrar approved the request for document preparation.')
                    add_notification(db, 'Request approved', f'{public_id} was approved for processing. Pickup date is not yet scheduled.', public_id)
                    message = f'{public_id} approved for processing. Schedule collection when ready.'
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': message}

    @app.post('/api/admin/requests/{public_id}/schedule', dependencies=[Depends(require_csrf)])
    def schedule_collection(public_id: str, payload: PickupSchedulePayload, request: Request,
                            user=Depends(require_staff)):
        ensure_id(public_id)
        try:
            appointment = datetime.fromisoformat(payload.pickup_at)
            appointment = (appointment.replace(tzinfo=MANILA) if appointment.tzinfo is None
                           else appointment.astimezone(MANILA))
        except (ValueError, TypeError):
            fail(400, 'Choose a valid pickup date and time.')
        if appointment < now() or appointment > now() + timedelta(days=365):
            fail(400, 'Pickup must be in the future and within 365 days.')
        note = ' '.join((payload.note or '').split())
        timestamp = now().isoformat()
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT * FROM requests WHERE public_id=?', (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
                if record['cancelled_at'] or record['declined_at'] or record['claimed_at'] or record['approved_at']:
                    fail(409, 'Cancelled, declined, claimed or scheduled requests cannot be rescheduled here.')
                if not record['decision_at']:
                    fail(409, 'First approve the request before setting a pickup schedule.')
                if record['status'] not in ('Processing', 'Processed', 'Ready for Release'):
                    fail(409, 'Prepare the documents before scheduling pickup.')
                db.execute('''UPDATE requests SET status='Ready for Release',approved_at=?,approved_by=?,
                    pickup_at=?,pickup_note=?,updated_at=? WHERE id=?''',
                    (timestamp,user['username'],appointment.isoformat(),note or None,timestamp,record['id']))
                readable = appointment.strftime('%B %d, %Y at %I:%M %p')
                add_event(db, record['id'], 'Ready for Release',
                          f'Registrar scheduled document collection for {readable}.' + (f' Instructions: {note}' if note else ''))
                add_notification(db, 'Pickup scheduled',
                                 f'{public_id} is ready for release on {readable}.',public_id)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'Pickup for {public_id} scheduled on {readable}.',
                'pickup_at': appointment.isoformat()}

    @app.post('/api/admin/requests/{public_id}/approve', dependencies=[Depends(require_csrf)])
    def approve_for_release(public_id: str, request: Request, user=Depends(require_staff)):
        """Only the registrar can authorize pickup; record a persistent audit trail."""
        ensure_id(public_id)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT id,status,claimed_at,approved_at,decision_at,portal_user_id,cancelled_at,declined_at FROM requests WHERE public_id=?',
                                    (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
                if record['claimed_at'] or record['cancelled_at'] or record['declined_at']:
                    fail(409, 'Closed requests cannot be approved for release.')
                if record['portal_user_id'] is not None:
                    fail(409, 'Use Approve Request first, then Schedule Pickup for registered users.')
                if record['approved_at']:
                    fail(409, 'This document has already been approved for release.')
                if record['status'] not in ('Processing', 'Processed', 'Ready for Release'):
                    fail(409, 'Process or prepare this request before approving its release.')
                timestamp = now().isoformat()
                updated = db.execute("""UPDATE requests
                    SET status='Ready for Release',approved_at=?,approved_by=?,updated_at=?
                    WHERE id=? AND approved_at IS NULL AND claimed_at IS NULL""",
                    (timestamp, user['username'], timestamp, record['id']))
                if updated.rowcount != 1:
                    fail(409, 'Request changed; refresh and try again.')
                add_event(db, record['id'], 'Ready for Release',
                          f'Registrar administrator approved release ({user["username"]})')
                add_notification(db, 'Approved for collection',
                                 f'{public_id} was approved by the registrar and is ready for collection.', public_id)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{public_id} approved and ready for release.',
                'request_id': public_id, 'approved_at': timestamp}

    @app.post('/api/admin/requests/{public_id}/claim', dependencies=[Depends(require_csrf)])
    def confirm_claim(public_id: str, request: Request, user=Depends(require_staff)):
        """Registrar confirms an actual handover; never infer pickup from processing."""
        ensure_id(public_id)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT id,status,claimed_at,approved_at,pickup_at,portal_user_id,cancelled_at,declined_at FROM requests WHERE public_id=?',
                                    (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
                if record['claimed_at'] is not None or record['cancelled_at'] or record['declined_at']:
                    fail(409, 'This request has already been closed.')
                if record['status'] != 'Ready for Release' or not record['approved_at']:
                    fail(409, 'The document needs explicit admin approval before it can be claimed.')
                if record['portal_user_id'] is not None and not record['pickup_at']:
                    fail(409, 'A registrar-assigned pickup appointment is required.')
                if record['pickup_at'] and datetime.fromisoformat(record['pickup_at']) > now():
                    fail(409, 'Collection cannot be confirmed before the scheduled pickup date and time.')
                timestamp = now().isoformat()
                # SQLite original status constraint remains valid; claimed_at
                # differentiates physical pickup from simple processing.
                result = db.execute('''UPDATE requests
                    SET status='Processed', claimed_at=?, claimed_by=?, updated_at=?,
                        processed_at=COALESCE(processed_at, ?)
                    WHERE id=? AND status='Ready for Release' AND approved_at IS NOT NULL AND claimed_at IS NULL''',
                    (timestamp, user['username'], timestamp, timestamp, record['id']))
                if result.rowcount != 1:
                    fail(409, 'This request was already updated. Please refresh.')
                add_event(db, record['id'], 'Claimed',
                          f'Document released and received; confirmed by registrar staff ({user["username"]})')
                add_notification(db, 'Document claimed',
                                 f'{public_id} was confirmed as received by the requester.', public_id)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{public_id} marked as claimed / released.',
                'request_id': public_id, 'claimed_at': timestamp}

    @app.get('/api/admin/notifications')
    def staff_notifications(request: Request, user=Depends(require_staff)):
        with connect(database) as db:
            records = [dict(row) for row in db.execute(
                'SELECT * FROM notifications ORDER BY id DESC LIMIT 100')]
            unread = db.execute('SELECT COUNT(*) AS n FROM notifications WHERE is_read=0').fetchone()['n']
        return {'notifications': records, 'unread': unread}

    @app.post('/api/admin/notifications/read-all', dependencies=[Depends(require_csrf)])
    def mark_read(request: Request, user=Depends(require_staff)):
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE notifications SET is_read=1 WHERE is_read=0')
            db.execute('COMMIT')
        return {'message': 'Notifications marked as read.'}

    @app.post('/api/admin/change-password', dependencies=[Depends(require_csrf)])
    def change_password(payload: ChangePassword, request: Request, user=Depends(require_staff)):
        new = payload.new_password
        if (len(new) < 10 or len(new) > 128 or not re.search(r'[a-z]', new)
                or not re.search(r'[A-Z]', new) or not re.search(r'\d', new)
                or not re.search(r'[^A-Za-z0-9]', new)):
            fail(400, 'Password needs 10+ characters with uppercase, lowercase, number and symbol.')
        if new == payload.current_password:
            fail(400, 'The new password must be different from the current password.')
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
                if not verify_password(payload.current_password, row['password_hash']):
                    fail(400, 'Current password is incorrect.')
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(new), user['id']))
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        request.session.clear()
        request.session['csrf'] = secrets.token_urlsafe(32)
        return {'message': 'Password changed. Please sign in again.', 'csrf_token': request.session['csrf']}

    @app.post('/api/admin/seed', dependencies=[Depends(require_csrf)])
    def demo_seed(payload: SeedDemo, request: Request, user=Depends(require_staff)):
        from datetime import timedelta
        examples = [
            'Alex Rivera', 'Jordan Reyes', 'Jamie Santos', 'Taylor Mendoza',
            'Casey Navarro', 'Morgan Flores', 'Samira Garcia', 'Riley Bautista',
            'Andrea Velasco', 'Carlos Dela Cruz', 'Bianca Ramos', 'Patricia Aquino',
        ]
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                for index in range(payload.count):
                    submitted = now().date() - timedelta(days=index % 10)
                    deadline = max(submitted, now().date() + timedelta(days=(index * 7) % 32 - 3))
                    insert_request(
                        db, name=examples[index % len(examples)],
                        document_type=DOCUMENT_TYPES[index % len(DOCUMENT_TYPES)],
                        category=list(CATEGORIES)[index % len(CATEGORIES)],
                        requester_type=('Student' if index % 2 == 0 else 'Alumni'),
                        deadline=deadline.isoformat(), submission_date=submitted.isoformat(), demo=True
                    )
                add_notification(db, 'Sample records loaded', f'{payload.count} simulated document requests added.')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{payload.count} demo requests have been added.'}

    return app
