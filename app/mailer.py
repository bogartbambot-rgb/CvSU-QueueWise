"""Account verification email delivery via Gmail API or Resend (HTTPS only).

Gmail OAuth uses an existing, owner-authorized send-only refresh token. Never
persist OAuth tokens, verification secrets, or message bodies to SQLite/logs.
Test mode captures an in-memory outbox without contacting Google or Resend.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import formataddr
import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

LOGGER = logging.getLogger('queuewise.email')

GMAIL_REQUIRED = ('GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN', 'GMAIL_SENDER_EMAIL')
RESEND_REQUIRED = ('RESEND_API_KEY', 'QUEUEWISE_EMAIL_FROM')


class EmailDeliveryError(Exception):
    """The configured provider did not accept a verification email."""


def _all_set(keys: tuple[str, ...]) -> bool:
    return all(os.environ.get(key, '').strip() for key in keys)


def email_provider() -> str | None:
    choice = os.environ.get('QUEUEWISE_EMAIL_PROVIDER', 'auto').strip().lower()
    if choice not in ('auto', 'gmail', 'resend'):
        return None
    if choice in ('auto', 'gmail') and _all_set(GMAIL_REQUIRED):
        return 'gmail'
    if choice in ('auto', 'resend') and _all_set(RESEND_REQUIRED):
        return 'resend'
    return None


def sender_configured(testing: bool = False) -> bool:
    if testing:
        return True
    if not email_provider():
        return False
    try:
        make_verification_url('configuration-check')
    except EmailDeliveryError:
        return False
    return True


def make_verification_url(token: str, testing: bool = False) -> str:
    public_url = os.environ.get('QUEUEWISE_PUBLIC_URL', '').rstrip('/')
    if testing and not public_url:
        public_url = 'http://testserver'
    parts = urlsplit(public_url)
    if (not parts.netloc or parts.username or parts.password or parts.query or parts.fragment
            or parts.scheme not in ('https', 'http')
            or (not testing and parts.scheme != 'https')):
        raise EmailDeliveryError('Configure QUEUEWISE_PUBLIC_URL as your full HTTPS Railway domain.')
    return f'{public_url}/#verify-email?token={token}'


def _message_text(name: str, url: str) -> str:
    return (
        f'Hello {name},\n\n'
        'Thank you for registering with CvSU QueueWise.\n'
        'Please verify your email address by opening this link, then pressing Verify Email:\n\n'
        f'{url}\n\n'
        'This link expires in 24 hours and can be used once.\n'
        'If you did not register, you can ignore this message.\n\n'
        'QueueWise Registrar Portal (academic prototype; not an official university service)'
    )


def _send_gmail(email: str, name: str, url: str) -> None:
    missing = [key for key in GMAIL_REQUIRED if not os.environ.get(key, '').strip()]
    if missing:
        raise EmailDeliveryError('Configure all four Gmail OAuth variables in Railway.')
    sender = os.environ['GMAIL_SENDER_EMAIL'].strip()
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', sender):
        raise EmailDeliveryError('GMAIL_SENDER_EMAIL must be the authorized Gmail address.')

    token_data = urlencode({
        'client_id': os.environ['GMAIL_CLIENT_ID'].strip(),
        'client_secret': os.environ['GMAIL_CLIENT_SECRET'].strip(),
        'refresh_token': os.environ['GMAIL_REFRESH_TOKEN'].strip(),
        'grant_type': 'refresh_token',
    }).encode('utf-8')
    refresh_request = Request(
        'https://oauth2.googleapis.com/token', data=token_data, method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urlopen(refresh_request, timeout=12) as response:
            credentials = json.load(response)
        access_token = credentials.get('access_token')
        if not isinstance(access_token, str) or not access_token:
            raise EmailDeliveryError('Google did not return an access token. Re-authorize the Gmail sender.')

        message = EmailMessage()
        message['From'] = formataddr(('CvSU QueueWise', sender))
        message['To'] = email
        message['Subject'] = 'Verify your email — CvSU QueueWise'
        message.set_content(_message_text(name, url))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')
        payload = json.dumps({'raw': raw}).encode('utf-8')
        send_request = Request(
            'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            data=payload, method='POST',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
        )
        with urlopen(send_request, timeout=15) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not result.get('id'):
            raise EmailDeliveryError('Gmail did not confirm delivery acceptance. Try again.')
    except HTTPError as exc:
        # Never log API response bodies: they may contain emails or sensitive data.
        LOGGER.warning('Gmail verification email failed (HTTP %s)', exc.code)
        if exc.code in (400, 401):
            raise EmailDeliveryError('Gmail authorization was rejected or expired. Re-authorize the Gmail sender.') from exc
        if exc.code == 403:
            raise EmailDeliveryError('Gmail access denied. Check Gmail API, gmail.send scope, sender and quotas.') from exc
        raise EmailDeliveryError('Google Gmail API could not send the verification email. Check Railway logs.') from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        LOGGER.warning('Gmail verification email error (%s)', type(exc).__name__)
        raise EmailDeliveryError('Gmail API is temporarily unreachable or returned an invalid response.') from exc


def _send_resend(email: str, name: str, url: str) -> None:
    key = os.environ.get('RESEND_API_KEY', '').strip()
    sender = os.environ.get('QUEUEWISE_EMAIL_FROM', '').strip()
    if not key or not sender:
        raise EmailDeliveryError('Configure the Resend sender and API key in Railway.')
    payload = json.dumps({
        'from': sender, 'to': [email],
        'subject': 'Verify your email — CvSU QueueWise', 'text': _message_text(name, url),
    }).encode('utf-8')
    request = Request(
        'https://api.resend.com/emails', data=payload, method='POST',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    )
    try:
        with urlopen(request, timeout=12) as response:
            if not 200 <= response.status < 300:
                raise EmailDeliveryError('Resend rejected the verification message.')
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        LOGGER.warning('Resend verification email error (%s)', type(exc).__name__)
        raise EmailDeliveryError('Resend could not send the verification email. Check Railway email settings.') from exc


def send_verification_email(email: str, name: str, token: str, *, testing=False, outbox=None) -> None:
    """Send a verification email; test mode stores only an in-memory mock outbox."""
    url = make_verification_url(token, testing)
    if testing:
        if outbox is not None:
            outbox.append({'to': email, 'name': name, 'url': url, 'token': token})
        return
    provider = email_provider()
    if provider == 'gmail':
        _send_gmail(email, name, url)
    elif provider == 'resend':
        _send_resend(email, name, url)
    else:
        raise EmailDeliveryError('Configure Gmail API OAuth credentials and QUEUEWISE_PUBLIC_URL in Railway.')
