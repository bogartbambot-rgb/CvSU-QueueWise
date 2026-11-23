"""Ensure the selected needed-by date is private to requester and visible to registrar."""
from tests._office_dates import open_day, open_time

from datetime import timedelta
from fastapi.testclient import TestClient
from app import create_app
from app.storage import now

PASSWORD='SecurePass2026!'

def csrf(c): return {'X-CSRF-Token':c.get('/api/bootstrap').json()['csrf_token']}

def register_login(c, role):
    body = {'full_name': 'Lorna Reyes' if role=='Alumni' else 'Maria Santos',
            'student_number': '2018-55443' if role=='Alumni' else '2026-65432',
            'email': role.lower()+'@example.com','account_type':role,
            'password':PASSWORD,'confirm_password':PASSWORD}
    assert c.post('/api/auth/register',json=body,headers=csrf(c)).status_code==201
    token=c.app.state.email_outbox[-1]['token']
    assert c.post('/api/auth/verify-email',json={'token':token},headers=csrf(c)).status_code==200
    assert c.post('/api/auth/requester-login',json={'email':body['email'],'password':PASSWORD,'account_type':role},headers=csrf(c)).status_code==200
    return body


def test_both_roles_need_date_kept_for_admin(tmp_path):
    with TestClient(create_app(str(tmp_path/'dates.db'),testing=True)) as c:
        date_needed=open_day(11).isoformat()
        for role in ['Student','Alumni']:
            user=register_login(c,role)
            req={'requester_name':user['full_name'],'requester_type':role,'student_number':user['student_number'],
                 'document_type':'Certificate of Grades','category':'Regular','purpose':'Needed for an application','date_reason':'My application closes next week.',
                 'deadline':date_needed}
            response=c.post('/api/requests',json=req,headers=csrf(c))
            assert response.status_code==201,response.text
            mine=c.get('/api/my/requests').json()['requests']
            assert len(mine)==1
            assert mine[0]['deadline']==date_needed
            assert c.post('/api/auth/logout',headers=csrf(c)).status_code==200
        assert c.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(c)).status_code==200
        all_requests=c.get('/api/admin/requests').json()['requests']
        assert len(all_requests)==2
        assert {r['requester_type'] for r in all_requests}=={'Student','Alumni'}
        assert all(r['deadline']==date_needed for r in all_requests)
