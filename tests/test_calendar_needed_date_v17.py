"""The student's calendar date is the actual required-by deadline in the request."""
from tests._office_dates import open_day, open_time

from datetime import timedelta
from fastapi.testclient import TestClient
from app import create_app
from app.storage import now


def csrf(c):
    return {'X-CSRF-Token':c.get('/api/bootstrap').json()['csrf_token']}


def student_login(c):
    body={'full_name':'Test Student','student_number':'2026-33333',
          'email':'student@example.com','account_type':'Student',
          'password':'SecurePass2026!','confirm_password':'SecurePass2026!'}
    assert c.post('/api/auth/register',json=body,headers=csrf(c)).status_code==201
    token=c.app.state.email_outbox[-1]['token']
    assert c.post('/api/auth/verify-email',json={'token':token},headers=csrf(c)).status_code==200
    assert c.post('/api/auth/requester-login',json={'email':body['email'],
                   'password':body['password'],'account_type':'Student'},headers=csrf(c)).status_code==200


def test_date_picker_is_embedded_in_request_form_for_both_roles(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'), testing=True)) as c:
        js=c.get('/static/js/app.js').text
        html=c.get('/').text
        for text in ('function dateNeededWidget()', 'needed-calendar', 'name="deadline"',
                     'toggle-needed-picker', 'apply-needed-date', 'data-needed-day',
                     'function chooseNeededDate(', '${dateNeededWidget()}',
                     'Date Needed', 'Date Needed / Reason'):
            assert text in js, text
        assert 'Academic Calendar' not in html
        assert 'id="calendarNavItem"' not in html
        assert 'function calendarPage()' not in js
        assert 'go-calendar' not in js
        assert 'v=1.12' in html
        assert 'queuewise-shell-v112' in c.get('/sw.js').text
        # Both Student and Alumni use a single role-neutral calendar widget.
        assert 'dateNeededWidget()' in js
        assert "${alumni?`<label" not in js


def test_selected_needed_date_persists_and_past_date_rejected(tmp_path):
    with TestClient(create_app(str(tmp_path/'needed.db'),testing=True)) as c:
        student_login(c)
        today=now().date()
        body={'requester_name':'Test Student','requester_type':'Student','student_number':'2026-33333',
              'document_type':'Certificate of Grades','category':'Regular',
              'purpose':'For a scholarship application','date_reason':'My scholarship deadline is near.','deadline':open_day(6, base=today).isoformat()}
        result=c.post('/api/requests',json=body,headers=csrf(c))
        assert result.status_code==201,result.text
        records=c.get('/api/my/requests').json()['requests']
        assert len(records)==1
        assert records[0]['deadline']==body['deadline']
        assert records[0]['status']=='Pending'
        invalid={**body,'deadline':(today-timedelta(days=2)).isoformat()}
        response=c.post('/api/requests',json=invalid,headers=csrf(c))
        assert response.status_code in (400,422),response.text
        assert len(c.get('/api/my/requests').json()['requests'])==1
