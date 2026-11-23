"""v1.12.6 registrar office calendar and time boundaries."""
from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient

from app import create_app, registrar_open_day, registrar_pickup_hour
from app.storage import now
from tests._office_dates import open_day


def csrf(client):
    return {'X-CSRF-Token': client.get('/api/bootstrap').json()['csrf_token']}


def payload(deadline):
    return {'requester_name': 'Ariana Lopez', 'document_type': 'Certificate of Grades',
            'category': 'Regular', 'purpose': 'Scholarship application',
            'date_reason': 'Records are needed for an academic scholarship deadline.',
            'deadline': deadline.isoformat()}


def register_student(client):
    body={'first_name':'Ariana','last_name':'Lopez','student_number':'2026-AB123',
          'email':'ariana@example.com','account_type':'Student',
          'password':'Strong2026!Password','confirm_password':'Strong2026!Password'}
    assert client.post('/api/auth/register',json=body,headers=csrf(client)).status_code == 201
    token=client.app.state.email_outbox[-1]['token']
    assert client.post('/api/auth/verify-email',json={'token':token},headers=csrf(client)).status_code == 200
    assert client.post('/api/auth/requester-login',json={
        'email':body['email'],'password':body['password']},headers=csrf(client)).status_code == 200


def staff_login(client):
    assert client.post('/api/auth/login',json={
        'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(client)).status_code == 200


def next_closed_weekend():
    today=now().date()
    # Next Friday, Saturday, Sunday (including this Friday if today is Friday).
    friday=today+timedelta(days=(4-today.weekday())%7 or 7)
    return [friday+timedelta(days=i) for i in range(3)]


def test_calendar_rule_rejects_all_three_closed_weekdays_and_accepts_open_dates(tmp_path):
    with TestClient(create_app(str(tmp_path/'request.db'),testing=True)) as c:
        register_student(c)
        for closed in next_closed_weekend():
            assert not registrar_open_day(closed)
            response=c.post('/api/requests',json=payload(closed),headers=csrf(c))
            assert response.status_code==400, (closed,response.text)
            assert 'Friday through Sunday' in response.json()['error']
        for future in (open_day(1),open_day(2)):
            assert registrar_open_day(future)
            response=c.post('/api/requests',json=payload(future),headers=csrf(c))
            assert response.status_code==201, response.text
        assert len(c.get('/api/my/requests').json()['requests'])==2


def test_pickup_and_rescheduling_enforce_weekdays_and_time_boundaries(tmp_path):
    db=str(tmp_path/'schedule.db')
    with TestClient(create_app(db,testing=True)) as owner, TestClient(create_app(db,testing=True)) as staff:
        register_student(owner)
        created=owner.post('/api/requests',json=payload(open_day(10)),headers=csrf(owner))
        assert created.status_code==201,created.text
        ref=created.json()['request']['id']
        staff_login(staff)
        assert staff.post(f'/api/admin/requests/{ref}/decision',json={'decision':'approve'},headers=csrf(staff)).status_code==200
        url=f'/api/admin/requests/{ref}/schedule'
        for closed in next_closed_weekend():
            response=staff.post(url,json={'pickup_at':f'{closed}T14:00'},headers=csrf(staff))
            assert response.status_code==400,response.text
            assert 'closed Friday through Sunday' in response.json()['error']
        day=open_day(2)
        for hour in ('00:00','07:59','17:00','17:01','23:00'):
            response=staff.post(url,json={'pickup_at':f'{day}T{hour}'},headers=csrf(staff))
            assert response.status_code==400,(hour,response.text)
            assert '8:00 AM to before 5:00 PM' in response.json()['error']
        assert staff.post(url,json={'pickup_at':f'{day}T08:00'},headers=csrf(staff)).status_code==200
        # A requester can ask for a new schedule after a missed pickup.
        with sqlite3.connect(db) as connection:
            connection.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                               (f'{now().date()-timedelta(days=4)}T15:00:00+08:00',ref))
        assert owner.get('/api/my/requests').json()['requests'][0]['status']=='Missed Pickup'
        response=owner.post(f'/api/my/requests/{ref}/request-reschedule',json={
            'reason':'I had an examination and was unable to visit the registrar.'},headers=csrf(owner))
        assert response.status_code==200,response.text
        for closed in next_closed_weekend():
            response=staff.post(url,json={'pickup_at':f'{closed}T10:00'},headers=csrf(staff))
            assert response.status_code==400,response.text
        reschedule_day=open_day(8)
        for hour in ('07:59','17:00'):
            response=staff.post(url,json={'pickup_at':f'{reschedule_day}T{hour}'},headers=csrf(staff))
            assert response.status_code==400,response.text
        approved=staff.post(url,json={'pickup_at':f'{reschedule_day}T16:59'},headers=csrf(staff))
        assert approved.status_code==200,approved.text
        result=owner.get('/api/my/requests').json()['requests'][0]
        assert result['status']=='Pickup Scheduled'
        assert result['reschedule_count']==1
        assert result['pickup_at'].startswith(f'{reschedule_day}T16:59')
        assert 'Friday through Sunday' in approved.json()['message']


def test_time_uses_manila_timezone_when_offsets_are_supplied():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    manila=ZoneInfo('Asia/Manila')
    assert registrar_pickup_hour(datetime(2026,11,23,8,0,tzinfo=manila))
    assert registrar_pickup_hour(datetime(2026,11,23,16,59,tzinfo=manila))
    assert not registrar_pickup_hour(datetime(2026,11,23,7,59,tzinfo=manila))
    assert not registrar_pickup_hour(datetime(2026,11,23,17,0,tzinfo=manila))
    assert not registrar_pickup_hour(datetime(2026,11,27,11,0,tzinfo=manila))
    assert registrar_pickup_hour(datetime(2026,11,23,0,30,tzinfo=ZoneInfo('UTC')))


def test_web_ui_disables_closed_days_and_informs_student_and_admin(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'),testing=True)) as c:
        script=c.get('/static/js/app.js').text
        html=c.get('/').text
        worker=c.get('/sw.js').text
    assert 'registrarDayOpen(key)' in script
    assert 'const key=dateKey(date), closed=!registrarDayOpen(key), disabled=' in script
    assert 'Friday–Sunday dates are unavailable' in script
    assert 'registrarPickupValid' in script
    assert 'id="pickupScheduleWarning"' in script
    assert 'Closed Friday–Sunday' in html
    assert 'v1.12.6' in html and 'v=1.12.6' in html
    assert 'queuewise-shell-v1126' in worker
