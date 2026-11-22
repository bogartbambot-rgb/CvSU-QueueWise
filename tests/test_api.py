import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.storage import connect, now


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('QUEUEWISE_ADMIN_PASSWORD', raising=False)
    app = create_app(str(tmp_path / 'queuewise.db'), testing=True)
    with TestClient(app) as client:
        yield client


def bootstrap(client):
    response=client.get('/api/bootstrap')
    assert response.status_code==200
    return response.json()['csrf_token']


def headers(client):
    return {'X-CSRF-Token':bootstrap(client)}


def login(client):
    response=client.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=headers(client))
    assert response.status_code==200, response.text
    return response.json()


def payload(**kw):
    fields={'requester_name':'Juan Dela Cruz','document_type':'Certificate of Grades',
            'category':'Graduating','deadline':(now().date()+timedelta(days=5)).isoformat()}
    fields.update(kw)
    return fields


def test_page_pwa_manifest_and_csp(client):
    assert client.get('/').status_code==200
    assert 'QueueWise' in client.get('/').text
    assert client.get('/sw.js').status_code==200
    assert client.get('/manifest.webmanifest').json()['short_name']=='QueueWise'
    assert client.get('/static/css/styles.css').status_code==200
    assert client.get('/static/js/app.js').status_code==200
    assert "frame-ancestors 'none'" in client.get('/').headers['Content-Security-Policy']
    assert client.get('/api/bootstrap').headers['Cache-Control']=='no-store'


def test_csrf_and_staff_permissions(client):
    assert client.post('/api/requests',json=payload()).status_code==403
    assert client.get('/api/admin/requests').status_code==401
    assert client.post('/api/admin/process-next',headers=headers(client)).status_code==401
    assert client.post('/api/auth/login',json={'username':'admin','password':'wrong'},headers=headers(client)).status_code==401
    assert client.get('/api/admin/notifications').status_code==401


def test_validate_bad_names_and_deadline(client):
    token=headers(client)
    for bad_name in ('', 'A', 'Juan', 'Juan 123', 'John D.', 'John 1Smith', '   '):
        response=client.post('/api/requests',json=payload(requester_name=bad_name),headers=token)
        assert response.status_code in (400,422), (bad_name,response.text)
    for bad_date in ('yesterday','2025-01-01','2026-02-30',
                     (now().date()+timedelta(days=365*4)).isoformat()):
        response=client.post('/api/requests',json=payload(deadline=bad_date),headers=token)
        assert response.status_code==400, (bad_date,response.text)
    for category in ('None','Unknown'):
        assert client.post('/api/requests',json=payload(category=category),headers=token).status_code==400
    assert client.post('/api/requests',json=payload(document_type='Random document'),headers=token).status_code==400
    assert client.get('/api/track/REQ-9999').status_code==404
    assert client.get('/api/track/REQUIRED').status_code==400
    login(client)
    assert client.get('/api/admin/requests').json()['stats']['total']==0


def test_public_submit_track_and_staff_process(client):
    submission=client.post('/api/requests',json=payload(),headers=headers(client))
    assert submission.status_code==201, submission.text
    created=submission.json()['request']
    assert created['id']=='REQ-0001'
    assert created['status']=='Pending'
    tracked=client.get('/api/track/REQ-0001').json()
    assert tracked['request']['status']=='Pending'
    assert tracked['events'][0]['status']=='Pending'
    assert 'requester_name' not in tracked['request']
    assert client.get('/api/admin/requests').status_code==401
    login(client)
    data=client.get('/api/admin/requests').json()
    assert data['stats']['total']==1 and data['stats']['heap_valid'] is True
    assert data['priority'][0]['public_id']=='REQ-0001'
    processed=client.post('/api/admin/process-next',headers=headers(client))
    assert processed.status_code==200, processed.text
    assert processed.json()['request_id']=='REQ-0001'
    assert client.get('/api/track/REQ-0001').json()['request']['status']=='Awaiting Approval'  # Processing is not permission to release
    after=client.get('/api/admin/requests').json()
    assert after['stats']['pending']==0 and after['stats']['processed']==1
    assert after['arrivals']==['REQ-0001']
    assert after['stats']['hash_entries']==1
    assert client.post('/api/admin/process-next',headers=headers(client)).status_code==409


def test_sequential_status_and_invalid_transition(client):
    first=client.post('/api/requests',json=payload(),headers=headers(client)).json()['request']['id']
    login(client)
    route=f'/api/admin/requests/{first}/status'
    assert client.patch(route,json={'status':'Ready for Release'},headers=headers(client)).status_code==409
    assert client.patch(route,json={'status':'Processing'},headers=headers(client)).status_code==200
    assert client.get('/api/admin/requests').json()['stats']['pending']==0
    assert client.patch(route,json={'status':'Processing'},headers=headers(client)).status_code==409
    assert client.patch(route,json={'status':'Ready for Release'},headers=headers(client)).status_code==409
    assert client.post(f'/api/admin/requests/{first}/approve',headers=headers(client)).status_code==200
    assert client.patch(route,json={'status':'Processed'},headers=headers(client)).status_code==409
    assert len(client.get(f'/api/track/{first}').json()['events'])==3
    assert client.patch(route,json={'status':'Processing'},headers=headers(client)).status_code==409


def test_stress_capacity_and_order_and_persistence(client):
    login(client)
    seeded=client.post('/api/admin/seed',json={'count':150},headers=headers(client))
    assert seeded.status_code==200, seeded.text
    data=client.get('/api/admin/requests').json()
    assert data['stats']['total']==150 and data['stats']['heap_valid']
    assert data['stats']['hash_entries']==150
    assert data['stats']['hash_buckets'] >= 256
    assert data['arrivals'][0]=='REQ-0001'
    assert data['arrivals'][-1]=='REQ-0150'
    assert all(data['priority'][i]['priority_score'] >= data['priority'][i+1]['priority_score']
               for i in range(len(data['priority'])-1))
    assert client.get('/api/track/REQ-0150').status_code==200
    assert len({r['public_id'] for r in data['requests']})==150
    for _ in range(3):
        assert client.post('/api/admin/process-next',headers=headers(client)).status_code==200
    assert client.get('/api/admin/requests').json()['stats']['processed']==3


def test_notifications_and_logout(client):
    client.post('/api/requests',json=payload(),headers=headers(client))
    login(client)
    inbox=client.get('/api/admin/notifications').json()
    assert inbox['unread']==1
    assert client.post('/api/admin/notifications/read-all',headers=headers(client)).status_code==200
    assert client.get('/api/admin/notifications').json()['unread']==0
    assert client.post('/api/auth/logout',headers=headers(client)).status_code==200
    assert client.get('/api/admin/requests').status_code==401


def test_change_password_requires_current_and_strength(client):
    login(client)
    url='/api/admin/change-password'
    assert client.post(url,json={'current_password':'wrong','new_password':'NewPassword@123'},headers=headers(client)).status_code==400
    assert client.post(url,json={'current_password':'CvSU@2026Demo!','new_password':'short'},headers=headers(client)).status_code==400
    changed=client.post(url,json={'current_password':'CvSU@2026Demo!','new_password':'NewPassword@123'},headers=headers(client))
    assert changed.status_code==200
    assert client.get('/api/admin/requests').status_code==401
    assert client.post('/api/auth/login',json={'username':'admin','password':'CvSU@2026Demo!'},headers=headers(client)).status_code==401
    assert client.post('/api/auth/login',json={'username':'admin','password':'NewPassword@123'},headers=headers(client)).status_code==200


def test_sqlite_persists_across_app_restart(tmp_path):
    path=str(tmp_path/'persistent.db')
    with TestClient(create_app(path, testing=True)) as first:
        item=first.post('/api/requests',json=payload(),headers=headers(first)).json()['request']
        assert item['id']=='REQ-0001'
    with TestClient(create_app(path, testing=True)) as reopened:
        tracked=reopened.get('/api/track/REQ-0001')
        assert tracked.status_code==200
        assert tracked.json()['request']['status']=='Pending'
        second=reopened.post('/api/requests',json=payload(requester_name='Maria Santos'),headers=headers(reopened))
        assert second.status_code==201
        assert second.json()['request']['id']=='REQ-0002'
        login(reopened)
        assert reopened.get('/api/admin/requests').json()['arrivals']==['REQ-0001','REQ-0002']


def test_concurrent_submissions_get_unique_ids(client):
    from concurrent.futures import ThreadPoolExecutor
    token=headers(client)
    def create(n):
        return client.post('/api/requests',json=payload(requester_name=f'Alex{n} Rivera'.replace(str(n),'') ), headers=token)
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(create,range(24)))
    assert all(response.status_code==201 for response in responses), [r.text for r in responses if r.status_code!=201]
    ids=[r.json()['request']['id'] for r in responses]
    assert len(ids)==len(set(ids))==24
    login(client)
    data=client.get('/api/admin/requests').json()
    assert data['stats']['total']==24
    assert data['stats']['heap_valid']
