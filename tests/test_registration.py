"""Student/alumni registration, request privacy, and backward-compatible persistence."""
from datetime import timedelta
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from app.storage import now

PASSWORD='SafePass2026!'


def csrf(c):
    return {'X-CSRF-Token': c.get('/api/bootstrap').json()['csrf_token']}


def registration(role='Student', number='2026-12345', email='student@example.com', name='Maria Santos'):
    return dict(account_type=role, student_number=number, email=email,
                full_name=name, password=PASSWORD, confirm_password=PASSWORD)


def register(c, **kwargs):
    response = c.post('/api/auth/register', json=registration(**kwargs), headers=csrf(c))
    if response.status_code == 201:
        token = c.app.state.email_outbox[-1]['token']
        verification = c.post('/api/auth/verify-email',json={'token':token},headers=csrf(c))
        assert verification.status_code == 200, verification.text
        email = registration(**kwargs)['email']
        logged_in = c.post('/api/auth/requester-login',json={'email':email,'password':PASSWORD},headers=csrf(c))
        assert logged_in.status_code == 200,logged_in.text
    return response


def submit(c, **kwargs):
    body=dict(requester_name='Spoofed Person', requester_type='Alumni', student_number='FAKE-99999',
              document_type='Certificate of Grades', category='Regular', purpose='Job application',
              deadline=(now().date()+timedelta(days=15)).isoformat()) | kwargs
    return c.post('/api/requests', json=body, headers=csrf(c))


def test_student_registration_private_dashboard_and_logout(tmp_path):
    with TestClient(create_app(str(tmp_path/'students.db'), testing=True)) as c:
        assert c.get('/api/my/requests').status_code == 401
        result=register(c)
        assert result.status_code == 201, result.text
        assert result.json()['user']['role'] == 'Student'
        assert result.json()['user']['student_number'] == '2026-12345'
        assert c.get('/api/bootstrap').json()['user']['role'] == 'Student'
        created=submit(c)
        assert created.status_code == 201, created.text
        own=c.get('/api/my/requests')
        assert own.status_code == 200
        assert len(own.json()['requests']) == 1
        assert own.json()['requests'][0]['purpose'] == 'Job application'
        assert c.get('/api/admin/requests').status_code == 401
        assert c.post('/api/admin/process-next',headers=csrf(c)).status_code == 401
        assert c.get('/api/my/notifications').json()['notifications'][0]['status'] == 'Pending'
        assert c.post('/api/auth/logout',headers=csrf(c)).status_code == 200
        assert c.get('/api/my/requests').status_code == 401
        wrong=c.post('/api/auth/requester-login',json={'email':'student@example.com','password':'WrongPass1!'},headers=csrf(c))
        assert wrong.status_code == 401
        good=c.post('/api/auth/requester-login',json={'email':'STUDENT@example.com','password':PASSWORD},headers=csrf(c))
        assert good.status_code == 200
        assert len(c.get('/api/my/requests').json()['requests']) == 1


def test_alumni_and_student_cannot_view_each_others_requests(tmp_path):
    db=str(tmp_path/'shared.db')
    with TestClient(create_app(db,testing=True)) as alice, TestClient(create_app(db,testing=True)) as bob:
        assert register(alice).status_code == 201
        request_id=submit(alice).json()['request']['id']
        assert register(bob, role='Alumni', number='2017-12345', email='alumni@example.com', name='Daniel Reyes').status_code == 201
        assert bob.get('/api/my/requests').json()['requests'] == []
        assert bob.get('/api/my/notifications').json()['notifications'] == []
        mine=submit(bob, purpose='Transfer documents')
        assert mine.status_code==201, mine.text
        assert bob.get('/api/my/requests').json()['requests'][0]['public_id'] != request_id
        assert len(alice.get('/api/my/requests').json()['requests']) == 1
        assert alice.get('/api/my/notifications').json()['notifications'][0]['public_id'] == request_id
    with sqlite3.connect(db) as conn:
        data=conn.execute('SELECT requester_name,requester_type,student_number,portal_user_id FROM requests ORDER BY id').fetchall()
        assert data[0][:3]==('Maria Santos','Student','2026-12345')
        assert data[1][:3]==('Daniel Reyes','Alumni','2017-12345')
        assert data[0][3] != data[1][3]


def test_bad_password_validation_no_duplicates_or_blank_purpose(tmp_path):
    with TestClient(create_app(str(tmp_path/'validation.db'),testing=True)) as c:
        invalid=registration();invalid['password']='abc';invalid['confirm_password']='abc'
        assert c.post('/api/auth/register',json=invalid,headers=csrf(c)).status_code == 400
        invalid=registration();invalid['confirm_password']='NotMatching1!'
        assert c.post('/api/auth/register',json=invalid,headers=csrf(c)).status_code == 400
        invalid=registration();invalid['student_number']='a!'
        assert c.post('/api/auth/register',json=invalid,headers=csrf(c)).status_code == 400
        invalid=registration();invalid['email']='notanemail'
        assert c.post('/api/auth/register',json=invalid,headers=csrf(c)).status_code == 400
        assert register(c).status_code==201
        assert register(c).status_code==409
        assert submit(c,purpose='').status_code==400
        assert submit(c,purpose='x').status_code==400
        assert c.get('/api/my/requests').json()['requests']==[]


def test_account_sqlite_migration_and_persistence(tmp_path):
    db=str(tmp_path/'migrated.db')
    with TestClient(create_app(db, testing=True)) as c:
        assert register(c, role='Alumni', number='2018-99999', email='alumni@example.com', name='Daniel Reyes').status_code==201
        assert submit(c,purpose='Certificate for employment').status_code==201
    with TestClient(create_app(db,testing=True)) as c:
        assert c.post('/api/auth/requester-login',json={'email':'alumni@example.com','password':PASSWORD},headers=csrf(c)).status_code==200
        assert len(c.get('/api/my/requests').json()['requests'])==1
    with sqlite3.connect(db) as conn:
        cols={row[1] for row in conn.execute('PRAGMA table_info(requests)')}
        assert {'student_number','purpose','portal_user_id'}<=cols
        assert conn.execute('SELECT count(*) FROM portal_users').fetchone()[0]==1


def test_registered_request_release_workflow(tmp_path):
    with TestClient(create_app(str(tmp_path/'flow.db'), testing=True)) as c:
        assert register(c).status_code==201
        request_id=submit(c).json()['request']['id']
        assert c.post('/api/auth/logout',headers=csrf(c)).status_code==200
        assert c.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(c)).status_code==200
        claim_url=f'/api/admin/requests/{request_id}/claim'
        assert c.post(claim_url, headers=csrf(c)).status_code==409
        assert c.patch(f'/api/admin/requests/{request_id}/status',json={'status':'Processing'},headers=csrf(c)).status_code==200
        assert c.patch(f'/api/admin/requests/{request_id}/status',json={'status':'Ready for Release'},headers=csrf(c)).status_code==409
        assert c.post(f'/api/admin/requests/{request_id}/approve',headers=csrf(c)).status_code==200
        assert c.post(claim_url,headers=csrf(c)).status_code==200
        assert c.post('/api/auth/logout',headers=csrf(c)).status_code==200
        assert c.post('/api/auth/requester-login',json={'email':'student@example.com','password':PASSWORD},headers=csrf(c)).status_code==200
        assert c.get('/api/my/requests').json()['requests'][0]['status']=='Claimed'
        assert c.get('/api/my/notifications').json()['notifications'][0]['status']=='Claimed'


def test_new_registration_ui_static_routes(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'), testing=True)) as c:
        ui=c.get('/static/js/app.js').text
        for term in ('function registerPage()', 'function requesterDashboard()', 'function myRequestsTable(', 
                     'id="registerForm"', 'id="requesterLoginForm"', 'id="requesterType"',
                     "view==='register'", 'data-auth-tab="staff"', 'id="requestForm"',
                     'function authFrame(', 'state.user?.role'):
            assert term in ui,term
        assert 'v=1.9' in c.get('/').text
        assert c.get('/manifest.webmanifest').status_code==200
