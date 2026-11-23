"""Regression tests for Student/Alumni admin views and confirmed receipt."""
from tests._office_dates import open_day, open_time

import sqlite3
from datetime import timedelta

from fastapi.testclient import TestClient

from app import create_app
from app.storage import now


def csrf(client):
    return {'X-CSRF-Token': client.get('/api/bootstrap').json()['csrf_token']}


def staff_login(client):
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'CvSU@2026Demo!'}, headers=csrf(client))
    assert r.status_code == 200, r.text


def create(client, role='Student', name='Maria Santos'):
    return client.post('/api/requests', headers=csrf(client), json={
        'requester_name': name, 'requester_type': role,
        'document_type': 'Certificate of Grades', 'category': 'Regular',
        'deadline': open_day(12).isoformat(),
    })


def test_admin_sees_students_and_alumni_but_guest_cannot(tmp_path):
    with TestClient(create_app(str(tmp_path / 'school.db'), testing=True)) as c:
        student = create(c, 'Student', 'Maria Santos')
        alumni = create(c, 'Alumni', 'Daniel Reyes')
        assert student.status_code == alumni.status_code == 201
        assert c.get('/api/admin/requests').status_code == 401
        tracked = c.get('/api/track/REQ-0001').json()['request']
        assert 'requester_name' not in tracked and 'requester_type' not in tracked
        staff_login(c)
        data = c.get('/api/admin/requests').json()
        assert data['stats']['students'] == 1
        assert data['stats']['alumni'] == 1
        assert data['stats']['total'] == 2
        assert {r['requester_type'] for r in data['requests']} == {'Student', 'Alumni'}
        assert data['stats']['heap_valid']
        assert data['arrivals'] == ['REQ-0001','REQ-0002']


def test_claimed_requires_readiness_and_stores_staff_and_time(tmp_path):
    db_path = tmp_path / 'claimed.db'
    with TestClient(create_app(str(db_path), testing=True)) as c:
        created = create(c).json()['request']['id']
        claim = f'/api/admin/requests/{created}/claim'
        # No guest access even if they know the ID or can get a CSRF token.
        assert c.post(claim, headers=csrf(c)).status_code == 401
        staff_login(c)
        assert c.post(claim, headers=csrf(c)).status_code == 409
        path = f'/api/admin/requests/{created}/status'
        assert c.patch(path, json={'status':'Processing'}, headers=csrf(c)).status_code == 200
        assert c.post(claim, headers=csrf(c)).status_code == 409
        assert c.patch(path, json={'status':'Ready for Release'}, headers=csrf(c)).status_code == 409
        assert c.post(f'/api/admin/requests/{created}/approve',headers=csrf(c)).status_code == 200
        result = c.post(claim, headers=csrf(c))
        assert result.status_code == 200, result.text
        assert result.json()['claimed_at']
        assert c.post(claim, headers=csrf(c)).status_code == 409  # No double handover
        assert c.patch(path, json={'status':'Processing'}, headers=csrf(c)).status_code == 409
        snapshot = c.get('/api/admin/requests').json()
        assert snapshot['stats']['claimed'] == 1
        assert snapshot['stats']['ready_to_claim'] == 0
        assert snapshot['stats']['pending'] == 0
        assert snapshot['stats']['heap_valid'] is True
        assert snapshot['arrivals'] == [created]
        assert snapshot['stats']['hash_entries'] == 1
        claimed = snapshot['claimed'][0]
        assert claimed['public_id'] == created
        assert claimed['claimed_by'] == 'admin'
        assert claimed['claimed_at']
        public = c.get(f'/api/track/{created}').json()
        assert public['request']['status'] == 'Claimed'
        assert public['request']['claimed_at']
        assert public['events'][-1]['status'] == 'Claimed'
        assert 'requester_name' not in public['request']
        assert any(x['title'] == 'Document claimed' for x in c.get('/api/admin/notifications').json()['notifications'])
    with TestClient(create_app(str(db_path), testing=True)) as restarted:
        assert restarted.get(f'/api/track/{created}').json()['request']['status'] == 'Claimed'
        staff_login(restarted)
        assert restarted.get('/api/admin/requests').json()['stats']['claimed'] == 1


def test_process_next_can_be_marked_ready_then_claimed(tmp_path):
    with TestClient(create_app(str(tmp_path / 'quick.db'), testing=True)) as c:
        request_id = create(c, 'Alumni', 'Daniel Reyes').json()['request']['id']
        staff_login(c)
        assert c.post('/api/admin/process-next', headers=csrf(c)).status_code == 200
        assert c.get(f'/api/track/{request_id}').json()['request']['status'] == 'Awaiting Approval'
        assert c.post(f'/api/admin/requests/{request_id}/claim', headers=csrf(c)).status_code == 409
        assert c.patch(f'/api/admin/requests/{request_id}/status',
                       json={'status':'Ready for Release'},headers=csrf(c)).status_code == 409
        assert c.post(f'/api/admin/requests/{request_id}/approve',headers=csrf(c)).status_code == 200
        assert c.post(f'/api/admin/requests/{request_id}/claim', headers=csrf(c)).status_code == 200
        assert c.get(f'/api/track/{request_id}').json()['request']['status'] == 'Claimed'


def test_missing_requester_type_is_unclassified_not_misreported(tmp_path):
    with TestClient(create_app(str(tmp_path / 'legacy-api.db'), testing=True)) as c:
        payload = {'requester_name':'Ana Silva', 'document_type':'Certificate of Grades',
                   'category':'Regular','deadline': open_day(1).isoformat()}
        assert c.post('/api/requests', json=payload, headers=csrf(c)).status_code == 201
        bad = c.post('/api/requests', json=payload | {'requester_type':'Teacher'}, headers=csrf(c))
        assert bad.status_code == 422
        staff_login(c)
        stats=c.get('/api/admin/requests').json()['stats']
        assert (stats['students'], stats['alumni'], stats['unclassified']) == (0,0,1)


def test_non_destructive_migration_of_existing_database(tmp_path):
    db_path = tmp_path / 'prior.db'
    with sqlite3.connect(db_path) as c:
        c.executescript('''
        CREATE TABLE requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE,
            requester_name TEXT NOT NULL,
            document_type TEXT NOT NULL,
            category TEXT NOT NULL,
            submission_date TEXT NOT NULL,
            deadline TEXT NOT NULL,
            priority_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Processing','Ready for Release','Processed')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            processed_at TEXT,
            demo INTEGER NOT NULL DEFAULT 0,
            CHECK(deadline >= submission_date)
        );
        INSERT INTO requests (public_id,requester_name,document_type,category,
                              submission_date,deadline,priority_score,status,created_at,updated_at)
          VALUES ('REQ-0001','Old Record','Certificate of Grades','Regular',
                  '2026-11-21','2026-12-21', 42,'Pending','2026-11-21T10:00:00+08:00','2026-11-21T10:00:00+08:00');
        ''')
    with TestClient(create_app(str(db_path), testing=True)) as c:
        staff_login(c)
        snapshot=c.get('/api/admin/requests').json()
        assert snapshot['requests'][0]['requester_type']=='Not specified'
        assert snapshot['requests'][0]['public_id']=='REQ-0001'
        assert snapshot['stats']['unclassified']==1
        assert create(c, 'Alumni').status_code == 201
        assert c.get('/api/admin/requests').json()['stats']['total']==2
    with sqlite3.connect(db_path) as c:
        cols=[r[1] for r in c.execute('PRAGMA table_info(requests)')]
        assert all(x in cols for x in ('requester_type','claimed_at','claimed_by'))


def test_frontend_has_claim_nav_filters_claim_action(tmp_path):
    with TestClient(create_app(str(tmp_path / 'ui.db'), testing=True)) as c:
        page=c.get('/').text
        js=c.get('/static/js/app.js').text
        assert 'id="claimedNavItem"' in page
        for part in ('function claimedPage()', 'function renderClaimedRows()',
                     "if (action==='mark-claimed')", 'id="requesterType"',
                     'id="requesterFilter"', 'function adminDashboard()',
                     "view==='claimed'", "if (view === 'claimed' && !isStaff())"):
            assert part in js
