"""v1.11 contract: one request may hold many documents; actions are role-safe.
Tests use a temporary SQLite database and stubbed email outbox, never real users.
"""
from tests._office_dates import open_day, open_time

from datetime import timedelta
import sqlite3
from fastapi.testclient import TestClient
from app import create_app
from app.storage import now

PASSWORD='Strong2026!Password'

def csrf(c): return {'X-CSRF-Token':c.get('/api/bootstrap').json()['csrf_token']}

def register(c, name='Ariana Lopez', number='2026-A1234', email='ariana@example.com', role='Student'):
    resp=c.post('/api/auth/register',json={'full_name':name,'student_number':number,'email':email,
       'account_type':role,'password':PASSWORD,'confirm_password':PASSWORD},headers=csrf(c))
    assert resp.status_code==201,resp.text
    token=c.app.state.email_outbox[-1]['token']
    assert c.post('/api/auth/verify-email',json={'token':token},headers=csrf(c)).status_code==200
    assert c.post('/api/auth/requester-login',json={'email':email,'password':PASSWORD},headers=csrf(c)).status_code==200

def submit(c, **changes):
    payload={'requester_name':'Ariana Lopez','document_type':'Certificate of Grades',
             'document_types':['Certificate of Grades','Transcript of Records (TOR)'],
             'category':'Regular','purpose':'Application for a school scholarship',
             'date_reason':'The scholarship application requires records by next month.',
             'deadline':open_day(20).isoformat()} | changes
    return c.post('/api/requests',json=payload,headers=csrf(c))

def admin(c):
    return c.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=csrf(c))

def decision(c,request_id,value='approve',reason=None):
    return c.post(f'/api/admin/requests/{request_id}/decision',json={'decision':value,'reason':reason},headers=csrf(c))

def schedule(c,request_id,hours=24):
    return c.post(f'/api/admin/requests/{request_id}/schedule',json={
        'pickup_at':((now()+timedelta(hours=hours)) if hours<0 else open_time(max(1,(hours+23)//24))).isoformat(), 'note':'Bring valid school ID'},headers=csrf(c))

def test_multiple_documents_one_request_id_and_justification_migration(tmp_path):
    db=str(tmp_path/'documents.db')
    with TestClient(create_app(db,testing=True)) as c:
        register(c)
        bad=submit(c,date_reason='No')
        assert bad.status_code==400
        assert submit(c,document_types=[]).status_code==400
        assert submit(c,document_types=['Certificate of Grades','Certificate of Grades']).status_code==400
        assert submit(c,document_types=['Certificate of Grades','Unknown type']).status_code==400
        r=submit(c)
        assert r.status_code==201,r.text
        record=c.get('/api/my/requests').json()['requests'][0]
        assert len(record['documents'])==2
        assert 'scholarship' in record['date_reason']
        assert len(c.get('/api/my/requests').json()['requests'])==1
        ref=record['public_id']
    with TestClient(create_app(db,testing=True)) as c:
        assert admin(c).status_code==200
        allrows=c.get('/api/admin/requests').json()['requests']
        assert len(allrows)==1
        assert allrows[0]['public_id']==ref
        assert len(allrows[0]['documents'])==2
        assert allrows[0]['date_reason']
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT COUNT(*) FROM request_documents').fetchone()[0]==2

def test_cancel_retracts_from_heap_but_keeps_history_and_blocks_others(tmp_path):
    db=str(tmp_path/'cancel.db')
    with TestClient(create_app(db,testing=True)) as owner, TestClient(create_app(db,testing=True)) as other:
        register(owner)
        ref=submit(owner).json()['request']['id']
        register(other, 'Bianca Santos', '2026-B4321', 'bianca@example.com')
        url=f'/api/my/requests/{ref}/cancel'
        assert other.post(url,json={'reason':'Incorrect documents'},headers=csrf(other)).status_code==404
        assert owner.post(url,json={'reason':'I selected the wrong document'},headers=csrf(owner)).status_code==200
        assert owner.post(url,json={},headers=csrf(owner)).status_code==409
        mine=owner.get('/api/my/requests').json()['requests'][0]
        assert mine['status']=='Cancelled'
        assert 'wrong document' in mine['cancelled_reason']
        # Public reference-ID trackers do not reveal private cancellation details.
        public=other.get(f'/api/track/{ref}').json()
        assert public['request']['status']=='Cancelled'
        assert 'wrong document' not in str(public)
        assert owner.post('/api/auth/logout',headers=csrf(owner)).status_code==200
        assert admin(owner).status_code==200
        snapshot=owner.get('/api/admin/requests').json()
        assert snapshot['stats']['pending']==0
        assert snapshot['stats']['cancelled']==1
        assert snapshot['arrivals']==[ref]
        assert owner.post('/api/admin/process-next',headers=csrf(owner)).status_code==409

def test_decline_reason_mandatory_and_visible_only_to_owner(tmp_path):
    db=str(tmp_path/'decline.db')
    with TestClient(create_app(db,testing=True)) as owner, TestClient(create_app(db,testing=True)) as staff:
        register(owner)
        ref=submit(owner).json()['request']['id']
        assert decision(owner,ref,'decline','Missing supporting document').status_code==401
        assert admin(staff).status_code==200
        assert decision(staff,ref,'decline','short').status_code==400
        r=decision(staff,ref,'decline','The requested records are not available for this test case.')
        assert r.status_code==200,r.text
        assert decision(staff,ref,'approve').status_code==409
        assert schedule(staff,ref).status_code==409
        assert staff.get('/api/admin/requests').json()['stats']['pending']==0
        assert owner.get('/api/my/requests').json()['requests'][0]['status']=='Declined'
        assert 'not available' in owner.get('/api/my/requests').json()['requests'][0]['declined_reason']
        assert 'not available' in str(owner.get('/api/my/notifications').json())
        public=owner.get(f'/api/track/{ref}').json()
        assert public['request']['status']=='Declined'
        assert 'not available' not in str(public)

def test_approve_schedule_and_no_early_collection(tmp_path):
    db=str(tmp_path/'schedule.db')
    with TestClient(create_app(db,testing=True)) as student, TestClient(create_app(db,testing=True)) as staff:
        register(student)
        ref=submit(student).json()['request']['id']
        assert admin(staff).status_code==200
        assert schedule(staff,ref).status_code==409
        assert decision(staff,ref,'approve').status_code==200
        assert decision(staff,ref,'approve').status_code==409
        assert schedule(staff,ref,hours=-1).status_code==400
        assert schedule(staff,ref,hours=24).status_code==200
        assert schedule(staff,ref,hours=48).status_code==409
        details=student.get('/api/my/requests').json()['requests'][0]
        assert details['status']=='Pickup Scheduled'
        assert details['pickup_at']
        assert details['pickup_note']=='Bring valid school ID'
        assert student.post(f'/api/my/requests/{ref}/cancel',json={},headers=csrf(student)).status_code==409
        assert staff.post(f'/api/admin/requests/{ref}/claim',headers=csrf(staff)).status_code==409
        # Only after actual appointment and handover.
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE requests SET pickup_at=? WHERE public_id=?',((now()-timedelta(minutes=5)).isoformat(),ref))
        assert staff.post(f'/api/admin/requests/{ref}/claim',headers=csrf(staff)).status_code==200
        assert student.get('/api/my/requests').json()['requests'][0]['status']=='Claimed'

def test_cancel_cannot_be_impersonated_and_status_bypass_blocked(tmp_path):
    with TestClient(create_app(str(tmp_path/'auth.db'),testing=True)) as c:
        register(c)
        ref=submit(c).json()['request']['id']
        assert c.patch(f'/api/admin/requests/{ref}/status',json={'status':'Processed'},headers=csrf(c)).status_code==401
        assert c.post(f'/api/admin/requests/{ref}/schedule',json={'pickup_at':open_time(2).isoformat()},headers=csrf(c)).status_code==401
        assert c.post('/api/auth/logout',headers=csrf(c)).status_code==200
        assert c.post(f'/api/my/requests/{ref}/cancel',json={},headers=csrf(c)).status_code==401

def test_user_interface_has_new_controls_and_no_university_brand(tmp_path):
    with TestClient(create_app(str(tmp_path/'ui.db'),testing=True)) as c:
        html=c.get('/').text
        js=c.get('/static/js/app.js').text
        assert 'Cavite State University' not in html+js
        assert 'CvSU ' not in html+js
        assert 'v1.12' in html
        for expected in ('reviewModal','cancelModal','cancelRequestForm'):
            assert expected in html
        for expected in ('doc-option-grid','date_reason','reviewRequestHtml','open-cancel','approve-request','decline-request','schedule-pickup'):
            assert expected in js
