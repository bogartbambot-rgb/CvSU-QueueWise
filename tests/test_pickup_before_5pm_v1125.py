"""5 PM Manila registrar closing-time policy for original and rescheduled pickups."""
from tests._office_dates import open_day, open_time

from datetime import datetime, timedelta
import sqlite3
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import create_app, missed_pickup
from app.storage import now

MANILA = ZoneInfo('Asia/Manila')
PASSWORD = 'Strong2026!Password'


def csrf(client):
    return {'X-CSRF-Token': client.get('/api/bootstrap').json()['csrf_token']}


def register_verified_student(client):
    response = client.post('/api/auth/register', json={
        'first_name': 'Ariana', 'last_name': 'Lopez', 'account_type': 'Student',
        'student_number': '2026-AB123', 'email': 'ariana@example.com',
        'password': PASSWORD, 'confirm_password': PASSWORD,
    }, headers=csrf(client))
    assert response.status_code == 201, response.text
    token = client.app.state.email_outbox[-1]['token']
    assert client.post('/api/auth/verify-email', json={'token': token}, headers=csrf(client)).status_code == 200
    assert client.post('/api/auth/requester-login', json={
        'email': 'ariana@example.com', 'password': PASSWORD,
    }, headers=csrf(client)).status_code == 200


def test_missed_pickup_starts_exactly_at_5pm_manila_and_not_at_appointment_hour():
    record = {
        'pickup_at': '2026-11-25T15:00:00+08:00',
        'approved_at': '2026-11-24T10:00:00+08:00',
        'claimed_at': None, 'cancelled_at': None, 'declined_at': None,
    }
    assert not missed_pickup(record, as_of=datetime(2026, 11, 25, 15, 1, tzinfo=MANILA))
    assert not missed_pickup(record, as_of=datetime(2026, 11, 25, 16, 59, 59, tzinfo=MANILA))
    assert missed_pickup(record, as_of=datetime(2026, 11, 25, 17, 0, tzinfo=MANILA))
    assert missed_pickup(record, as_of=datetime(2026, 11, 26, 10, 0, tzinfo=MANILA))
    assert missed_pickup(record, as_of=datetime(2026, 11, 25, 9, 0, tzinfo=ZoneInfo('UTC')))
    record['claimed_at'] = '2026-11-25T16:30:00+08:00'
    assert not missed_pickup(record, as_of=datetime(2026, 11, 25, 18, 0, tzinfo=MANILA))


def test_initial_and_rescheduled_pickups_both_reject_5pm_or_later(tmp_path):
    path = str(tmp_path / 'cutoff.db')
    with TestClient(create_app(path, testing=True)) as student, TestClient(create_app(path, testing=True)) as staff:
        register_verified_student(student)
        response = student.post('/api/requests', json={
            'requester_name': 'Ariana Lopez',
            'document_type': 'Certificate of Grades',
            'category': 'Regular',
            'purpose': 'Scholarship',
            'date_reason': 'These are needed to complete my scholarship documents.',
            'deadline': open_day(30).isoformat(),
        }, headers=csrf(student))
        assert response.status_code == 201, response.text
        ref = response.json()['request']['id']
        response = staff.post('/api/auth/login', json={
            'username': 'admin', 'password': 'CvSU@2026Demo!',
        }, headers=csrf(staff))
        assert response.status_code == 200, response.text
        assert staff.post(f'/api/admin/requests/{ref}/decision', json={
            'decision': 'approve',
        }, headers=csrf(staff)).status_code == 200

        day = open_day(2)
        schedule = f'/api/admin/requests/{ref}/schedule'
        for hour in ('17:00', '17:01', '22:00'):
            response = staff.post(schedule, json={'pickup_at': f'{day}T{hour}'}, headers=csrf(staff))
            assert response.status_code == 400, response.text
            assert 'before 5:00 PM' in response.json()['error']
        first = staff.post(schedule, json={'pickup_at': f'{day}T16:59', 'note': 'Bring ID'}, headers=csrf(staff))
        assert first.status_code == 200, first.text
        assert 'before 5:00 PM' in first.json()['message']
        mine = student.get('/api/my/requests').json()['requests'][0]
        assert mine['pickup_at'].startswith(f'{day}T16:59')
        assert '5:00 PM' in str(student.get('/api/my/notifications').json())

        # Simulate an older missed appointment without waiting two real days.
        old_day = now().date() - timedelta(days=2)
        with sqlite3.connect(path) as con:
            con.execute('UPDATE requests SET pickup_at=? WHERE public_id=?', (f'{old_day}T15:00:00+08:00', ref))
        assert student.get('/api/my/requests').json()['requests'][0]['status'] == 'Missed Pickup'
        response = student.post(f'/api/my/requests/{ref}/request-reschedule', json={
            'reason': 'I had a required academic examination on the scheduled day.',
        }, headers=csrf(student))
        assert response.status_code == 200, response.text
        next_day = open_day(4)
        for hour in ('17:00', '18:30'):
            response = staff.post(schedule, json={'pickup_at': f'{next_day}T{hour}'}, headers=csrf(staff))
            assert response.status_code == 400, response.text
        response = staff.post(schedule, json={'pickup_at': f'{next_day}T16:45'}, headers=csrf(staff))
        assert response.status_code == 200, response.text
        assert 'rescheduled' in response.json()['message']
        assert '5:00 PM' in response.json()['message']
        mine = student.get('/api/my/requests').json()['requests'][0]
        assert mine['status'] == 'Pickup Scheduled'
        assert mine['reschedule_count'] == 1


def test_pickup_reminder_shows_in_student_and_admin_ui(tmp_path):
    with TestClient(create_app(str(tmp_path / 'ui.db'), testing=True)) as client:
        script = client.get('/static/js/app.js').text
        css = client.get('/static/css/styles.css').text
        html = client.get('/').text
        service_worker = client.get('/static/js/sw.js').text
    assert 'PICKUP_CUTOFF_NOTE' in script
    assert 'before 5:00 PM (Philippine time)' in script
    assert 'pickup-cutoff-note' in script and '.pickup-cutoff-note' in css
    assert 'v1.12.6' in html
    assert 'queuewise-shell-v1126' in service_worker


def test_same_day_5pm_cutoff_changes_request_status_and_emits_one_event(tmp_path, monkeypatch):
    """The whole day need not pass: at 5 PM Manila the portal shows Missed Pickup."""
    import importlib
    api_module = importlib.import_module('app')
    path = str(tmp_path / 'same-day.db')
    with TestClient(create_app(path, testing=True)) as owner, TestClient(create_app(path, testing=True)) as staff:
        register_verified_student(owner)
        new = owner.post('/api/requests', json={
            'requester_name': 'Ariana Lopez',
            'document_type': 'Certificate of Grades', 'category': 'Regular',
            'purpose': 'Scholarship',
            'date_reason': 'I need it for a university scholarship application.',
            'deadline': open_day(30).isoformat(),
        }, headers=csrf(owner))
        assert new.status_code == 201, new.text
        ref = new.json()['request']['id']
        assert staff.post('/api/auth/login', json={
            'username': 'admin', 'password': 'CvSU@2026Demo!',
        }, headers=csrf(staff)).status_code == 200
        assert staff.post(f'/api/admin/requests/{ref}/decision', json={
            'decision': 'approve',
        }, headers=csrf(staff)).status_code == 200
        scheduled_day = open_day(2)
        assert staff.post(f'/api/admin/requests/{ref}/schedule', json={
            'pickup_at': f'{scheduled_day}T14:00',
        }, headers=csrf(staff)).status_code == 200
        # Pretend that collection day has arrived but closing time has not.
        with sqlite3.connect(path) as con:
            con.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                        (f'{now().date()}T14:00:00+08:00', ref))
        current_day = now().date()
        monkeypatch.setattr(api_module, 'now', lambda: datetime.combine(
            current_day, datetime.strptime('16:59:59', '%H:%M:%S').time(), tzinfo=MANILA))
        assert owner.get('/api/my/requests').json()['requests'][0]['status'] == 'Ready for Release'
        monkeypatch.setattr(api_module, 'now', lambda: datetime.combine(
            current_day, datetime.strptime('17:00:00', '%H:%M:%S').time(), tzinfo=MANILA))
        assert owner.get('/api/my/requests').json()['requests'][0]['status'] == 'Missed Pickup'
        assert staff.get('/api/admin/requests').json()['stats']['missed_pickup'] == 1
        assert staff.post(f'/api/admin/requests/{ref}/claim', headers=csrf(staff)).status_code == 409
        owner.get('/api/my/requests')
        staff.get('/api/admin/requests')
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT COUNT(*) FROM request_events WHERE status='Missed Pickup'").fetchone()[0] == 1
