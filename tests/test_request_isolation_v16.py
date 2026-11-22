"""Privacy regression: each verified account sees ONLY its own requests and events.

Backend owns the filter; client-supplied requester name and category cannot expose
another person's records. Student and Alumni users share no private list.
"""
from datetime import timedelta
from fastapi.testclient import TestClient
from app import create_app
from app.storage import now

PASSWORD='GoodPassword2026!'

def csrf(client): return {'X-CSRF-Token':client.get('/api/bootstrap').json()['csrf_token']}

def register_and_verify(client, name, number, email, role):
    data={'full_name':name,'student_number':number,'email':email,'account_type':role,
          'password':PASSWORD,'confirm_password':PASSWORD}
    assert client.post('/api/auth/register',json=data,headers=csrf(client)).status_code==201
    token=client.app.state.email_outbox[-1]['token']
    assert client.post('/api/auth/verify-email',json={'token':token},headers=csrf(client)).status_code==200
    assert client.post('/api/auth/requester-login',json={'email':email,'password':PASSWORD,'account_type':role},headers=csrf(client)).status_code==200

def create_request(client, doc='Certificate of Grades', purpose='Scholarship paperwork'):
    body={'requester_name':'NOT MY NAME','requester_type':'Alumni','student_number':'OTHER-NO',
          'document_type':doc,'category':'Regular','purpose':purpose,
          'date_reason':'The document is required for a scheduled academic deadline.',
          'deadline':(now().date()+timedelta(days=10)).isoformat()}
    response=client.post('/api/requests',json=body,headers=csrf(client))
    assert response.status_code==201,response.text
    return response.json()['request']['id']

def test_two_students_and_alumni_have_strictly_separate_documents(tmp_path):
    db=str(tmp_path/'shared.db')
    with TestClient(create_app(db,testing=True)) as student_a, TestClient(create_app(db,testing=True)) as student_b, TestClient(create_app(db,testing=True)) as alumni:
        register_and_verify(student_a,'Maria Santos','2026-A1111','maria@example.com','Student')
        register_and_verify(student_b,'Carla Reyes','2026-B2222','carla@example.com','Student')
        register_and_verify(alumni,'Daniel Cruz','2019-C3333','daniel@example.com','Alumni')
        a1=create_request(student_a, purpose='Maria scholarship')
        a2=create_request(student_a, purpose='Maria transfer')
        b1=create_request(student_b, purpose='Carla scholarship')
        c1=create_request(alumni, purpose='Daniel employment')
        for client, expected_ids in ((student_a,[a2,a1]),(student_b,[b1]),(alumni,[c1])):
            result=client.get('/api/my/requests')
            assert result.status_code==200
            records=result.json()['requests']
            assert [r['public_id'] for r in records]==expected_ids
            assert all('requester_name' not in r and 'email' not in r and 'student_number' not in r for r in records)
            notifications=client.get('/api/my/notifications').json()['notifications']
            assert {item['public_id'] for item in notifications}==set(expected_ids)
            assert client.get('/api/admin/requests').status_code==401
        # Know another person's request ID? Still no account-private list leakage.
        # The legacy public tracker only returns a minimal ID/status, never personal details.
        public=student_b.get(f'/api/track/{a1}').json()
        assert not {'requester_name','purpose','document_type','student_number','email'} & public['request'].keys()
        assert student_b.get('/api/my/requests').json()['requests'][0]['public_id']==b1
        assert student_a.post('/api/auth/logout',headers=csrf(student_a)).status_code==200
        assert student_a.get('/api/my/requests').status_code==401
        assert alumni.get('/api/my/requests').json()['requests'][0]['public_id']==c1

def test_frontend_document_request_defaults_to_private_list(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'),testing=True)) as c:
        src=c.get('/static/js/app.js').text
        for token in ("requestMode: 'mine'", 'My Requests (${mine.length})', "action==='my-requests'",
                      "action==='new-request'", 'myRequestsTable(mine)', 'Private to you',
                      'Only documents you requested are listed here.'):
            assert token in src,token
        html=c.get('/').text
        assert 'v=1.12' in html


def test_production_rejects_guest_submissions_without_verified_account(tmp_path):
    with TestClient(create_app(str(tmp_path/'production.db'),testing=False)) as c:
        body={'requester_name':'Guest User','requester_type':'Student','student_number':'2026-45678',
              'document_type':'Certificate of Grades','category':'Regular','purpose':'Enrollment records',
              'deadline':(now().date()+timedelta(days=5)).isoformat()}
        result=c.post('/api/requests',json=body,headers=csrf(c))
        assert result.status_code==401
        assert 'verify your email' in result.json()['error']
        # A staff session cannot impersonate a student/alumni requester.
        assert c.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(c)).status_code==200
        assert c.post('/api/requests',json=body,headers=csrf(c)).status_code==401
        assert c.get('/api/my/requests').status_code==401
