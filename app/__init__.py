"""CvSU QueueWise API, PWA delivery, and staff-only registrar operations."""
from __future__ import annotations

from datetime import date, timedelta
import hmac
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
from .storage import (connect, init_database, get_secret, now, verify_password,
                      hash_password, fetch_records, persist_scores,
                      insert_request, add_notification, add_event)

LOGGER = logging.getLogger('queuewise')
ROOT = Path(__file__).resolve().parent
PUBLIC_ID_RE = re.compile(r'^REQ-\d{4,}$')
WORD_RE = re.compile(r"^[^\W\d_]+(?:['.\-][^\W\d_]+)*$", flags=re.UNICODE)
ALLOWED_TRANSITIONS = {
    'Pending': {'Processing', 'Processed'},
    'Processing': {'Ready for Release', 'Processed'},
    'Ready for Release': {'Processed'},
    'Processed': set(),
}


class LoginPayload(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=256)


class NewRequest(BaseModel):
    requester_name: str = Field(max_length=200)
    document_type: str
    category: str
    deadline: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class ChangeStatus(BaseModel):
    status: Literal['Processing', 'Ready for Release', 'Processed']


class SeedDemo(BaseModel):
    count: int = Field(default=12, ge=1, le=150)


def fail(status_code: int, message: str):
    raise HTTPException(status_code=status_code, detail=message)


def require_csrf(request: Request):
    token = request.session.get('csrf')
    received = request.headers.get('x-csrf-token', '')
    if not token or not hmac.compare_digest(token, received):
        fail(403, 'Security token expired. Refresh the page and try again.')


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
    name = ' '.join(value.strip().split())
    words = name.split(' ')
    if not 2 <= len(name) <= 60 or len(words) < 2 or any(
        len(''.join(ch for ch in word if ch.isalpha())) < 2 or WORD_RE.fullmatch(word) is None
        for word in words
    ):
        fail(400, 'Enter a complete first and last name (2–60 letters/characters; no numbers).')
    return name


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


def read_staff_snapshot(db) -> dict:
    """Refresh on every priority-sensitive view; the heap is a separate ADT."""
    records = fetch_records(db)
    engine = QueueEngine(records)
    engine.refresh(now().date())
    persist_scores(db, records)
    ranked = engine.ranked()
    all_records = sorted(records, key=lambda rec: rec['arrival_number'], reverse=True)
    counts = {status: sum(r['status'] == status for r in records)
              for status in ALLOWED_TRANSITIONS}
    return {
        'requests': all_records,
        'priority': ranked,
        'arrivals': engine.arrivals.traverse(),
        'next_id': engine.heap.peek(),
        'stats': {
            'total': len(records),
            'pending': counts['Pending'],
            'processing': counts['Processing'],
            'ready': counts['Ready for Release'],
            'processed': counts['Processed'],
            'hash_buckets': engine.hash_table.capacity,
            'hash_entries': engine.hash_table.size,
            'heap_entries': len(engine.heap.items),
            'heap_valid': engine.heap.valid(),
        },
        'refreshed_at': now().isoformat(),
    }


def create_app(db_path: str | None = None, testing: bool = False) -> FastAPI:
    database = str(Path(db_path) if db_path else ROOT.parent / 'instance' / 'queuewise.db')
    secret = get_secret(database)
    demo_password = os.environ.get('QUEUEWISE_ADMIN_PASSWORD', 'CvSU@2026Demo!')
    init_database(database, demo_password)
    app = FastAPI(title='CvSU QueueWise', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = database
    app.state.testing = testing
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
                    user = dict(record)
                else:
                    request.session.pop('staff_id', None)
        return {
            'csrf_token': request.session['csrf'], 'user': user,
            'today': now().date().isoformat(),
            'documents': DOCUMENT_TYPES, 'categories': list(CATEGORIES),
            'demo': True,
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
                'user': {'id': user['id'], 'username': user['username'], 'display_name': user['display_name']}}

    @app.post('/api/auth/logout', dependencies=[Depends(require_csrf)])
    def logout(request: Request):
        request.session.clear()
        request.session['csrf'] = secrets.token_urlsafe(32)
        return {'message': 'Signed out.', 'csrf_token': request.session['csrf']}

    @app.post('/api/requests', status_code=201, dependencies=[Depends(require_csrf)])
    def submit_request(payload: NewRequest, request: Request):
        name, deadline, submitted = validate_new_request(payload)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                engine = QueueEngine(fetch_records(db))
                result = insert_request(db, name=name, document_type=payload.document_type,
                                        category=payload.category, deadline=deadline,
                                        submission_date=submitted)
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
            events = [
                {'status': row['status'], 'message': row['message'], 'created_at': row['created_at']}
                for row in db.execute('SELECT status,message,created_at FROM request_events WHERE request_id=? ORDER BY id',
                                      (record['id'],))
            ]
        return {'request': {'id': record['public_id'], 'status': record['status'],
                            'submitted_at': record['submission_date'], 'updated_at': record['updated_at'],
                            'processed_at': record['processed_at']}, 'events': events}

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
                db.execute('UPDATE requests SET status=?,processed_at=?,updated_at=? WHERE id=? AND status=?',
                           ('Processed', timestamp, timestamp, chosen['id'], 'Pending'))
                add_event(db, chosen['id'], 'Processed', 'Registrar has processed this request')
                add_notification(db, 'Request processed', f'{chosen["public_id"]} was processed by registrar staff.', chosen['public_id'])
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{chosen["public_id"]} has been processed.', 'request_id': chosen['public_id']}

    @app.patch('/api/admin/requests/{public_id}/status', dependencies=[Depends(require_csrf)])
    def update_status(public_id: str, payload: ChangeStatus, request: Request, user=Depends(require_staff)):
        ensure_id(public_id)
        with connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                record = db.execute('SELECT * FROM requests WHERE public_id=?', (public_id,)).fetchone()
                if record is None:
                    fail(404, 'Request not found.')
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
                        deadline=deadline.isoformat(), submission_date=submitted.isoformat(), demo=True
                    )
                add_notification(db, 'Sample records loaded', f'{payload.count} simulated document requests added.')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'message': f'{payload.count} demo requests have been added.'}

    return app
