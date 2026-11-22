"""Email verification: security, persistence, migration, resend, delivery failure."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app import create_app
from app.mailer import EmailDeliveryError

PASSWORD='SecurePass2026!'


def csrf(client):
    return {'X-CSRF-Token':client.get('/api/bootstrap').json()['csrf_token']}


def payload(email='student@example.com', number='2026-12345'):
    return {'full_name':'Maria Santos','account_type':'Student','student_number':number,
            'email':email,'password':PASSWORD,'confirm_password':PASSWORD}


def create_client(tmp_path):
    return TestClient(create_app(str(tmp_path/'verify.db'),testing=True))


def register(client, **kwargs):
    return client.post('/api/auth/register',json=payload(**kwargs),headers=csrf(client))


def login(client):
    return client.post('/api/auth/requester-login',json={'email':'student@example.com','password':PASSWORD},headers=csrf(client))


def verify(client, token):
    return client.post('/api/auth/verify-email',json={'token':token},headers=csrf(client))


def test_register_sends_link_only_after_account_creation_and_blocks_login(tmp_path):
    with create_client(tmp_path) as c:
        r=register(c)
        assert r.status_code==201, r.text
        assert r.json()['requires_verification'] is True
        assert c.get('/api/bootstrap').json()['user'] is None
        assert c.get('/api/my/requests').status_code==401
        assert login(c).status_code==403
        item=c.app.state.email_outbox[-1]
        assert item['to']=='student@example.com'
        assert '#verify-email?token=' in item['url']
        with sqlite3.connect(c.app.state.db_path) as db:
            row=db.execute('SELECT email_verified_at FROM portal_users WHERE email=?',('student@example.com',)).fetchone()
            assert row == (None,)
            # Verify the raw token never appears in the SQLite file.
            assert item['token'].encode() not in Path(c.app.state.db_path).read_bytes()
        assert verify(c,item['token']).status_code==200
        assert login(c).status_code==200
        assert c.get('/api/bootstrap').json()['user']['role']=='Student'
        assert verify(c,item['token']).status_code==400  # one use only
        assert c.get('/api/my/requests').status_code==200


def test_invalid_and_expired_tokens_cannot_activate(tmp_path):
    with create_client(tmp_path) as c:
        assert register(c).status_code==201
        item=c.app.state.email_outbox[-1]
        assert verify(c,'a'*43).status_code==400
        assert verify(c,'invalid').status_code==422
        with sqlite3.connect(c.app.state.db_path) as db:
            db.execute("UPDATE email_verification_tokens SET expires_at=?",
                       ((datetime.now(timezone.utc)-timedelta(seconds=3)).isoformat(),))
        assert verify(c,item['token']).status_code==400
        assert login(c).status_code==403


def test_resend_cooldown_expiration_and_old_token_revoked(tmp_path):
    with create_client(tmp_path) as c:
        assert register(c).status_code==201
        old=c.app.state.email_outbox[-1]['token']
        url='/api/auth/resend-verification'
        r=c.post(url,json={'email':'student@example.com'},headers=csrf(c))
        assert r.status_code==429
        with sqlite3.connect(c.app.state.db_path) as db:
            db.execute("UPDATE email_verification_tokens SET last_sent_at=?",
                       ((datetime.now(timezone.utc)-timedelta(seconds=65)).isoformat(),))
        resent=c.post(url,json={'email':'student@example.com'},headers=csrf(c))
        assert resent.status_code==200,resent.text
        new=c.app.state.email_outbox[-1]['token']
        assert old!=new
        assert verify(c,old).status_code==400
        assert verify(c,new).status_code==200
        assert login(c).status_code==200
        # Unknown email and already verified email get the same generic response.
        known=c.post(url,json={'email':'student@example.com'},headers=csrf(c)).json()
        unknown=c.post(url,json={'email':'nobody@example.com'},headers=csrf(c)).json()
        assert known==unknown


def test_resend_rate_limit(tmp_path):
    with create_client(tmp_path) as c:
        register(c)
        with sqlite3.connect(c.app.state.db_path) as db:
            db.execute("UPDATE email_verification_tokens SET sent_count=5,last_sent_at=?",
                       ((datetime.now(timezone.utc)-timedelta(seconds=100)).isoformat(),))
        result=c.post('/api/auth/resend-verification',json={'email':'student@example.com'},headers=csrf(c))
        assert result.status_code==429


def test_migration_preserves_preverification_account(tmp_path):
    import app.storage as storage
    db=str(tmp_path/'migration.db')
    # Simulate existing v1.4 portal_users before the new column was introduced.
    with sqlite3.connect(db) as conn:
        conn.execute('''CREATE TABLE portal_users (
           id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
           account_type TEXT NOT NULL, student_number TEXT UNIQUE NOT NULL,
           email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('INSERT INTO portal_users (full_name,account_type,student_number,email,password_hash,created_at) VALUES (?,?,?,?,?,?)',
                     ('Maria Santos','Student','2026-12345','student@example.com',storage.hash_password(PASSWORD),datetime.now(timezone.utc).isoformat()))
    with TestClient(create_app(db,testing=True)) as c:
        assert login(c).status_code==200
        assert c.get('/api/my/requests').status_code==200
        with sqlite3.connect(db) as conn:
            assert conn.execute('SELECT email_verified_at FROM portal_users').fetchone()[0] is not None


def test_delivery_failure_stays_unverified_and_can_retry(tmp_path, monkeypatch):
    import app as backend
    def raise_delivery(*args,**kwargs):
        raise EmailDeliveryError('Email provider not reachable.')
    with create_client(tmp_path) as c:
        monkeypatch.setattr(backend,'send_verification_email',raise_delivery)
        result=register(c)
        assert result.status_code==503
        assert login(c).status_code==403
        # Failed send must not lock resend behind the 60-second cooldown.
        monkeypatch.undo()
        resent=c.post('/api/auth/resend-verification',json={'email':'student@example.com'},headers=csrf(c))
        assert resent.status_code==200,resent.text
        assert verify(c,c.app.state.email_outbox[-1]['token']).status_code==200


def test_ui_includes_verify_and_resend_routes(tmp_path):
    with create_client(tmp_path) as c:
        frontend=c.get('/static/js/app.js').text
        assert 'function verifyEmailPage()' in frontend
        assert "view==='verify-email'" in frontend
        assert 'id="resendVerificationForm"' in frontend
        assert "api('/api/auth/verify-email'" in frontend
        assert 'v=1.9' in c.get('/').text
        assert c.get('/manifest.webmanifest').status_code==200
