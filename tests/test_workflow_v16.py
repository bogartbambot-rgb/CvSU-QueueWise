"""Regression checks for portal links, verification and admin release approvals."""
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app import create_app

PASSWORD='SecurePass2026!'

def headers(c): return {'X-CSRF-Token':c.get('/api/bootstrap').json()['csrf_token']}
def admin(c):
    return c.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=headers(c))

def test_student_register_entry_on_login_and_calendar_ui(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'),testing=True)) as c:
        text=c.get('/static/js/app.js').text
        assert 'data-register-role="Student"' in text and 'data-register-role="Alumni"' in text
        assert "action==='register-student'" in text
        assert 'function dateNeededWidget()' in text
        assert 'data-needed-day=' in text and 'apply-needed-date' in text
        html=c.get('/').text
        assert 'id="calendarNavItem"' not in html
        assert 'v=1.12' in html
        assert c.get('/manifest.webmanifest').status_code==200

def test_only_registrar_can_approve_before_picking_up(tmp_path):
    with TestClient(create_app(str(tmp_path/'approval.db'),testing=True)) as c:
        assert admin(c).status_code==200
        data={'requester_name':'Maya Cruz','requester_type':'Student','student_number':'2026-34567','purpose':'Scholarship',
              'document_type':'Transcript of Records (TOR)','category':'Regular','deadline':(date.today()+timedelta(days=5)).isoformat()}
        r=c.post('/api/requests',json=data,headers=headers(c))
        assert r.status_code==201,r.text
        rid=r.json()['request']['id']
        claim=lambda: c.post(f'/api/admin/requests/{rid}/claim',headers=headers(c))
        approve=lambda: c.post(f'/api/admin/requests/{rid}/approve',headers=headers(c))
        assert claim().status_code==409
        assert approve().status_code==409
        assert c.patch(f'/api/admin/requests/{rid}/status',json={'status':'Ready for Release'},headers=headers(c)).status_code==409
        assert c.patch(f'/api/admin/requests/{rid}/status',json={'status':'Processing'},headers=headers(c)).status_code==200
        assert claim().status_code==409
        assert approve().status_code==200
        assert approve().status_code==409
        assert claim().status_code==200
        assert claim().status_code==409
        snapshot=c.get('/api/admin/requests').json()
        assert snapshot['stats']['claimed']==1
        assert snapshot['claimed'][0]['approved_at']
        assert c.post('/api/auth/logout',headers=headers(c)).status_code==200
        assert approve().status_code==401

def test_approval_persists_across_database_restart(tmp_path):
    db=str(tmp_path/'restart.db')
    with TestClient(create_app(db,testing=True)) as c:
        assert admin(c).status_code==200
        data={'requester_name':'Luna Smith','requester_type':'Alumni','student_number':'2019-33333','purpose':'Employment',
              'document_type':'Certificate of Grades','category':'Job Applicant','deadline':(date.today()+timedelta(days=5)).isoformat()}
        r=c.post('/api/requests',json=data,headers=headers(c))
        assert r.status_code==201,r.text
        rid=r.json()['request']['id']
        assert c.post('/api/admin/process-next',headers=headers(c)).status_code==200
        assert c.get(f'/api/track/{rid}').json()['request']['status']=='Awaiting Approval'
        assert c.post(f'/api/admin/requests/{rid}/approve',headers=headers(c)).status_code==200
    with TestClient(create_app(db,testing=True)) as c:
        assert c.get(f'/api/track/{rid}').json()['request']['status']=='Ready for Release'
        assert admin(c).status_code==200
        assert c.post(f'/api/admin/requests/{rid}/claim',headers=headers(c)).status_code==200
