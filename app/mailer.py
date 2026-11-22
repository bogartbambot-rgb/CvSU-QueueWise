"""Transactional verification emails via Resend's HTTPS API (no SMTP ports needed).

Verification URLs have tokens in URL fragments, avoiding server access-log leaks.
The raw token is not stored in SQLite and must never be included in application logs.
"""
from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LOGGER = logging.getLogger('queuewise.email')


class EmailDeliveryError(Exception):
    """The provider did not accept a verification email."""


def sender_configured(testing: bool = False) -> bool:
    if testing:
        return True
    return bool(os.environ.get('RESEND_API_KEY') and
                os.environ.get('QUEUEWISE_EMAIL_FROM') and
                os.environ.get('QUEUEWISE_PUBLIC_URL'))


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


def send_verification_email(email: str, name: str, token: str, *, testing=False, outbox=None) -> None:
    """Send with Resend; in tests, capture the message without contacting the internet."""
    url = make_verification_url(token, testing)
    if testing:
        if outbox is not None:
            outbox.append({'to': email, 'name': name, 'url': url, 'token': token})
        return
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    sender = os.environ.get('QUEUEWISE_EMAIL_FROM', '').strip()
    if not api_key or not sender:
        raise EmailDeliveryError('Configure RESEND_API_KEY and QUEUEWISE_EMAIL_FROM in Railway Variables.')
    # No HTML injection: the email uses plain text only.
    plain = (
        f'Hello {name},\n\n'
        'Thank you for registering with CvSU QueueWise.\n'
        'Please verify your email address by opening this link, then pressing Verify Email:\n\n'
        f'{url}\n\n'
        'This link expires in 24 hours and can be used once.\n'
        'If you did not register, you can ignore this message.\n\n'
        'QueueWise Registrar Portal (academic prototype; not an official university service)'
    )
    body = json.dumps({'from': sender, 'to': [email],
                       'subject': 'Verify your email — CvSU QueueWise', 'text': plain}).encode('utf-8')
    request = Request('https://api.resend.com/emails', data=body, method='POST',
                      headers={'Authorization': f'Bearer {api_key}',
                               'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=12) as response:
            if not 200 <= response.status < 300:
                raise EmailDeliveryError('Email provider rejected the verification message.')
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        # Never log the token or API key. The provider detail may contain an address.
        LOGGER.warning('Verification email delivery failed (%s)', type(exc).__name__)
        raise EmailDeliveryError('Verification email could not be sent. Check Railway email settings or try again.') from exc
