"""Regression tests for separated names, safe migration, and request flow."""
from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app import create_app
from app.storage import now

PASS = 'StrongPass2026!'


def csrf(client):
    return {'X-CSRF-Token': client.get('/api/bootstrap').json()['csrf_token']}


def registration(**updates):
    return dict(first_name='Mary Jane', middle_name='A.', last_name='Dela Cruz',
                account_type='Student', student_number='2026-55421',
                email='student@example.com', password=PASS,
                confirm_password=PASS) | updates


@pytest.mark.parametrize('role', ['Student', 'Alumni'])
def test_split_name_registration_verification_profile_and_request(tmp_path, role):
    with TestClient(create_app(str(tmp_path/'names.db'), testing=True)) as client:
        payload=registration(account_type=role)
        result=client.post('/api/auth/register',json=payload,headers=csrf(client))
        assert result.status_code==201, result.text
        with sqlite3.connect(client.app.state.db_path) as db:
            record=db.execute('SELECT full_name,first_name,middle_name,last_name FROM portal_users').fetchone()
            assert record==('Mary Jane A. Dela Cruz','Mary Jane','A.','Dela Cruz')
        token=client.app.state.email_outbox[-1]['token']
        assert client.post('/api/auth/verify-email',json={'token':token},headers=csrf(client)).status_code==200
        assert client.post('/api/auth/requester-login',json={'email':'student@example.com','password':PASS},headers=csrf(client)).status_code==200
        assert client.get('/api/bootstrap').json()['user']['display_name']=='Mary Jane A. Dela Cruz'
        request_payload={'requester_name':'Mary Jane A. Dela Cruz', 'document_type':'Transcript of Records',
                         'category':'Regular', 'purpose':'Scholarship application', 'deadline':(now().date()+timedelta(days=7)).isoformat(),
                         'date_reason':'Enrollment documentation is due next week.'}
        # Some document lists use TOR rather than spelled-out name.
        request_payload['document_type']=client.get('/api/bootstrap').json()['documents'][0]
        result=client.post('/api/requests',json=request_payload,headers=csrf(client))
        assert result.status_code==201,result.text
        assert len(client.get('/api/my/requests').json()['requests'])==1


def test_middle_name_truly_optional_and_hyphenated_names(tmp_path):
    with TestClient(create_app(str(tmp_path/'optional.db'), testing=True)) as client:
        data=registration(first_name=' Ana-Maria ',middle_name='  ',last_name="O'Neil")
        result=client.post('/api/auth/register',json=data,headers=csrf(client))
        assert result.status_code==201,result.text
        with sqlite3.connect(client.app.state.db_path) as db:
            assert db.execute('SELECT full_name,first_name,middle_name,last_name FROM portal_users').fetchone()==('Ana-Maria O\'Neil','Ana-Maria',None,"O'Neil")


@pytest.mark.parametrize('bad',[
    {'first_name':' '}, {'last_name':''}, {'first_name':'J'},
    {'last_name':'C.'}, {'first_name':'John123'},
    {'middle_name':'123'}, {'middle_name':'!'},{'first_name':'<script>'},
    {'first_name':None}, {'last_name':None},
])
def test_invalid_component_name_does_not_create_account(tmp_path, bad):
    with TestClient(create_app(str(tmp_path/'invalid.db'), testing=True)) as client:
        result=client.post('/api/auth/register',json=registration(**bad),headers=csrf(client))
        assert result.status_code in (400,422),result.text
        with sqlite3.connect(client.app.state.db_path) as db:
            assert db.execute('SELECT count(*) FROM portal_users').fetchone()[0]==0


def test_legacy_full_name_registration_backward_compatible(tmp_path):
    with TestClient(create_app(str(tmp_path/'legacy.db'), testing=True)) as client:
        data=registration()
        for field in ('first_name','middle_name','last_name'):
            data.pop(field)
        data['full_name']='Maria Santos'
        result=client.post('/api/auth/register',json=data,headers=csrf(client))
        assert result.status_code==201,result.text
        with sqlite3.connect(client.app.state.db_path) as db:
            assert db.execute('SELECT full_name,first_name,middle_name,last_name FROM portal_users').fetchone()==('Maria Santos',None,None,None)


def test_old_existing_account_survives_name_columns_migration(tmp_path):
    from app.storage import hash_password
    path=str(tmp_path/'old.db')
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE portal_users (id INTEGER PRIMARY KEY AUTOINCREMENT,
           full_name TEXT NOT NULL, account_type TEXT NOT NULL, student_number TEXT NOT NULL UNIQUE,
           email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
           email_verified_at TEXT)''')
        db.execute('''INSERT INTO portal_users (full_name, account_type, student_number, email,
          password_hash,created_at,email_verified_at) VALUES (?,?,?,?,?,?,?)''',
          ('Old Account','Student','2025-10001','old@example.com',hash_password(PASS),now().isoformat(),now().isoformat()))
    with TestClient(create_app(path, testing=True)) as client:
        assert client.post('/api/auth/requester-login',json={'email':'old@example.com','password':PASS},headers=csrf(client)).status_code==200
        assert client.get('/api/bootstrap').json()['user']['display_name']=='Old Account'
        with sqlite3.connect(path) as db:
            cols={row[1] for row in db.execute('PRAGMA table_info(portal_users)')}
            assert {'first_name','middle_name','last_name'} <= cols
            assert db.execute('SELECT full_name FROM portal_users WHERE email=?',('old@example.com',)).fetchone()[0]=='Old Account'


def test_frontend_has_three_field_controls_and_updated_pwa(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'),testing=True)) as client:
        js=client.get('/static/js/app.js').text
        assert 'name="first_name"' in js
        assert 'name="middle_name"' in js
        assert 'name="last_name"' in js
        assert '<label class="form-label">Full name ' not in js
        assert 'name="full_name"' not in js.split('function registerPage()')[1].split('function switchRegistrationRole(')[0]
        assert 'queuewise-shell-v1123' in client.get('/sw.js').text
        assert 'v1.12.3' in client.get('/').text
