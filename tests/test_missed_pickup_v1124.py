"""Missed appointments are reconciled, retained and rescheduled safely."""
from tests._office_dates import open_day, open_time

from datetime import timedelta
import sqlite3
from fastapi.testclient import TestClient
from app import create_app
from app.storage import now

PASSWORD = 'Strong2026!Password'

def csrf(client):
    return {'X-CSRF-Token': client.get('/api/bootstrap').json()['csrf_token']}

def enroll(client, email='sample@example.com', student='2026-AB123', name='Maria Lopez'):
    response = client.post('/api/auth/register', json={
        'first_name': name.split()[0], 'last_name': name.split()[-1],
        'account_type': 'Student','email': email,'student_number':student,
        'password':PASSWORD,'confirm_password':PASSWORD
    },headers=csrf(client))
    assert response.status_code == 201,response.text
    token=client.app.state.email_outbox[-1]['token']
    assert client.post('/api/auth/verify-email',json={'token':token},headers=csrf(client)).status_code==200
    assert client.post('/api/auth/requester-login',json={'email':email,'password':PASSWORD},headers=csrf(client)).status_code==200

def new_request(client):
    result=client.post('/api/requests',json={
        'requester_name':'Maria Lopez', 'document_type':'Certificate of Grades',
        'category':'Regular','date_reason':'I need the record for an academic scholarship application.',
        'purpose':'Scholarship','deadline':open_day(18).isoformat()
    },headers=csrf(client))
    assert result.status_code==201,result.text
    return result.json()['request']['id']

def staff_login(client):
    result=client.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(client))
    assert result.status_code==200,result.text

def approve_schedule(client,ref):
    result=client.post(f'/api/admin/requests/{ref}/decision',json={'decision':'approve'},headers=csrf(client))
    assert result.status_code==200,result.text
    result=client.post(f'/api/admin/requests/{ref}/schedule',json={'pickup_at':open_time(2).isoformat()},headers=csrf(client))
    assert result.status_code==200,result.text

def test_missed_pickup_after_whole_day_not_same_day(tmp_path):
    database=str(tmp_path/'missed.db')
    with TestClient(create_app(database,testing=True)) as student, TestClient(create_app(database,testing=True)) as staff:
        enroll(student)
        ref=new_request(student)
        staff_login(staff)
        approve_schedule(staff,ref)
        with sqlite3.connect(database) as db:
            db.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                       (now().replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),ref))
        # No show is not declared at the scheduled hour while the day is ongoing.
        assert student.get('/api/my/requests').json()['requests'][0]['status']=='Ready for Release'
        assert staff.get('/api/admin/requests').json()['stats']['missed_pickup']==0
        with sqlite3.connect(database) as db:
            db.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                       ((now()-timedelta(days=1)).isoformat(),ref))
        missed=student.get('/api/my/requests').json()['requests'][0]
        assert missed['status']=='Missed Pickup'
        assert missed['missed_at']
        assert missed['pickup_at']
        assert staff.get('/api/admin/requests').json()['stats']['missed_pickup']==1
        assert staff.post(f'/api/admin/requests/{ref}/claim',headers=csrf(staff)).status_code==409
        # Reads cannot emit duplicate missed notifications.
        student.get('/api/my/notifications')
        student.get('/api/my/requests')
        staff.get('/api/admin/requests')
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT COUNT(*) FROM request_events WHERE status='Missed Pickup'").fetchone()[0]==1
            assert db.execute("SELECT COUNT(*) FROM notifications WHERE title='Missed pickup'").fetchone()[0]==1

def test_reschedule_request_private_admin_approval_and_history(tmp_path):
    database=str(tmp_path/'reschedule.db')
    with TestClient(create_app(database,testing=True)) as owner, TestClient(create_app(database,testing=True)) as staff, TestClient(create_app(database,testing=True)) as other:
        enroll(owner)
        ref=new_request(owner)
        enroll(other,'other@example.com','2026-CD456','Bianca Santos')
        staff_login(staff)
        approve_schedule(staff,ref)
        with sqlite3.connect(database) as db:
            db.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                       ((now()-timedelta(days=2)).isoformat(),ref))
        assert owner.get('/api/my/requests').json()['requests'][0]['status']=='Missed Pickup'
        endpoint=f'/api/my/requests/{ref}/request-reschedule'
        assert owner.post(endpoint,json={'reason':'No'},headers=csrf(owner)).status_code==422
        assert other.post(endpoint,json={'reason':'I need to change the pickup date'},headers=csrf(other)).status_code==404
        assert staff.post(endpoint,json={'reason':'I will be late to collect it'},headers=csrf(staff)).status_code==401
        response=owner.post(endpoint,json={'reason':'I could not come because I had an examination.'},headers=csrf(owner))
        assert response.status_code==200,response.text
        assert owner.post(endpoint,json={'reason':'I also had a conflict.'},headers=csrf(owner)).status_code==409
        mine=owner.get('/api/my/requests').json()['requests'][0]
        assert mine['status']=='Reschedule Requested'
        assert 'examination' in mine['reschedule_reason']
        snapshot=staff.get('/api/admin/requests').json()
        assert snapshot['stats']['reschedule_requested']==1
        assert snapshot['requests'][0]['reschedule_reason']
        assert staff.post(f'/api/admin/requests/{ref}/claim',headers=csrf(staff)).status_code==409
        new_time=open_time(5).isoformat()
        response=staff.post(f'/api/admin/requests/{ref}/schedule',json={'pickup_at':new_time,'note':'Come to the registrar'},headers=csrf(staff))
        assert response.status_code==200,response.text
        assert 'rescheduled' in response.json()['message']
        mine=owner.get('/api/my/requests').json()['requests'][0]
        assert mine['status']=='Pickup Scheduled'
        assert mine['missed_at'] is None
        assert mine['reschedule_requested_at'] is None
        assert mine['reschedule_count']==1
        assert mine['pickup_at']==new_time
        with sqlite3.connect(database) as db:
            events=[v[0] for v in db.execute('SELECT status FROM request_events')]
            assert 'Missed Pickup' in events
            assert 'Reschedule Requested' in events
            assert 'Pickup Rescheduled' in events
            assert db.execute('SELECT COUNT(*) FROM request_documents WHERE request_id=(SELECT id FROM requests WHERE public_id=?)',(ref,)).fetchone()[0]==1
        # Same-day physical collection after the newly scheduled time can be confirmed.
        with sqlite3.connect(database) as db:
            db.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                       (now().replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),ref))
        assert staff.post(f'/api/admin/requests/{ref}/claim',headers=csrf(staff)).status_code==200
        assert owner.get('/api/my/requests').json()['requests'][0]['status']=='Claimed'
        assert owner.post(endpoint,json={'reason':'I missed the date again'},headers=csrf(owner)).status_code==409

def test_registrar_proactive_reschedule_after_no_show(tmp_path):
    database=str(tmp_path/'proactive.db')
    with TestClient(create_app(database,testing=True)) as owner, TestClient(create_app(database,testing=True)) as staff:
        enroll(owner)
        ref=new_request(owner)
        staff_login(staff)
        approve_schedule(staff,ref)
        # No arbitrary editing of active scheduled future appointments.
        assert staff.post(f'/api/admin/requests/{ref}/schedule',json={'pickup_at':open_time(7).isoformat()},headers=csrf(staff)).status_code==409
        with sqlite3.connect(database) as db:
            db.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',
                       ((now()-timedelta(days=1)).isoformat(),ref))
        staff.get('/api/admin/requests')
        updated=staff.post(f'/api/admin/requests/{ref}/schedule',json={'pickup_at':open_time(6).isoformat()},headers=csrf(staff))
        assert updated.status_code==200,updated.text
        assert owner.get('/api/my/requests').json()['requests'][0]['status']=='Pickup Scheduled'
