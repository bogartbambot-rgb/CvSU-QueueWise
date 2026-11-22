"""Gmail API mock tests; NEVER contact Google or deliver real email."""
import base64
from email import policy
from email.parser import BytesParser
from io import BytesIO
import json
from urllib.error import HTTPError

import pytest
from app import create_app
from app import mailer
from fastapi.testclient import TestClient


def gmail_env(monkeypatch):
    for key in mailer.RESEND_REQUIRED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('QUEUEWISE_EMAIL_PROVIDER', 'gmail')
    monkeypatch.setenv('GMAIL_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('GMAIL_CLIENT_SECRET', 'test-client-secret')
    monkeypatch.setenv('GMAIL_REFRESH_TOKEN', 'test-refresh-token')
    monkeypatch.setenv('GMAIL_SENDER_EMAIL', 'registrar.sender@gmail.com')
    monkeypatch.setenv('QUEUEWISE_PUBLIC_URL', 'https://queuewise.up.railway.app')


class FakeResponse:
    def __init__(self, data):
        self.stream = BytesIO(json.dumps(data).encode())
    def read(self, *args):
        return self.stream.read(*args)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.stream.close()


def test_gmail_oauth_send_only_link_and_mime(monkeypatch):
    gmail_env(monkeypatch)
    requests = []
    def mock_urlopen(request, timeout):
        requests.append((request, timeout))
        if 'oauth2.googleapis.com/token' in request.full_url:
            body = request.data.decode()
            assert 'grant_type=refresh_token' in body
            assert 'test-refresh-token' in body
            return FakeResponse({'access_token': 'mock-access-token'})
        assert request.full_url.endswith('/gmail/v1/users/me/messages/send')
        assert request.get_header('Authorization') == 'Bearer mock-access-token'
        data = json.loads(request.data)
        mime_bytes = base64.urlsafe_b64decode(data['raw'])
        msg = BytesParser(policy=policy.default).parsebytes(mime_bytes)
        assert msg['From'].addresses[0].addr_spec == 'registrar.sender@gmail.com'
        assert msg['To'].addresses[0].addr_spec == 'student@example.com'
        assert msg['Subject'] == 'Verify your email — QueueWise'
        assert '#verify-email?token=mock-token' in msg.get_content()
        return FakeResponse({'id': 'mock-google-message-id'})

    monkeypatch.setattr(mailer, 'urlopen', mock_urlopen)
    assert mailer.sender_configured() is True
    mailer.send_verification_email('student@example.com','Maria Santos','mock-token')
    assert len(requests)==2


def test_gmail_invalid_refresh_token_returns_safe_error(monkeypatch):
    gmail_env(monkeypatch)
    def invalid_token(request, timeout):
        raise HTTPError(request.full_url, 400, 'invalid_grant', {}, BytesIO(b'{"error":"invalid_grant"}'))
    monkeypatch.setattr(mailer, 'urlopen', invalid_token)
    with pytest.raises(mailer.EmailDeliveryError,match='Re-authorize the Gmail sender') as err:
        mailer.send_verification_email('student@example.com','Maria Santos','token')
    assert 'test-refresh-token' not in str(err.value)


def test_gmail_config_missing_or_insecure_url_rejected(monkeypatch):
    gmail_env(monkeypatch)
    monkeypatch.delenv('GMAIL_REFRESH_TOKEN')
    assert not mailer.sender_configured()
    monkeypatch.setenv('GMAIL_REFRESH_TOKEN', 'token')
    monkeypatch.setenv('QUEUEWISE_PUBLIC_URL', 'http://not-secure.com')
    with pytest.raises(mailer.EmailDeliveryError, match='full HTTPS'):
        mailer.send_verification_email('student@example.com','Maria Santos','token')


def test_account_registration_can_use_gmail_sender(monkeypatch, tmp_path):
    gmail_env(monkeypatch)
    # API test mode uses mock outbox, but the same backend accepts the OAuth settings.
    with TestClient(create_app(str(tmp_path/'mock.db'), testing=True)) as c:
        token = c.get('/api/bootstrap').json()['csrf_token']
        r = c.post('/api/auth/register', json={
            'full_name': 'Maria Santos', 'account_type':'Student', 'student_number':'2026-12345',
            'email':'student@example.com', 'password':'SecurePass2026!',
            'confirm_password':'SecurePass2026!',
        }, headers={'X-CSRF-Token':token})
        assert r.status_code == 201, r.text
        assert len(c.app.state.email_outbox) == 1
