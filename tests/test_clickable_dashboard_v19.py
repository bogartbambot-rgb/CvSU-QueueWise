from pathlib import Path
from fastapi.testclient import TestClient
from app import create_app


def test_dashboard_cards_are_routed_and_pwa_cache_is_refreshed(tmp_path):
    with TestClient(create_app(str(tmp_path / "cards.db"), testing=True)) as client:
        html=client.get('/').text
        js=client.get('/static/js/app.js').text
        css=client.get('/static/css/styles.css').text
        assert 'v=1.12' in html
        assert 'v1.12' in html
        assert 'queuewise-shell-v112' in client.get('/sw.js').text
        for path in ('tracked','active','completed','portal'):
            assert path in js
        for heading in ('My Tracked Requests','Active Requests','Completed Requests','Online Portal'):
            assert heading in js
        assert 'function dashboardStat(' in js
        assert 'function dashboardDetailPage(' in js
        assert "action==='open-dashboard-card'" in js
        assert 'data-detail=' in js
        assert 'type="button" class="stat-card stat-card-link"' in js
        assert 'stat-card-link:focus-visible' in css
        assert 'Back to Dashboard' in js


def test_dashboard_detail_pages_scope_data_to_authenticated_account():
    js=Path(__file__).resolve().parents[1].joinpath('app/static/js/app.js').read_text(encoding='utf-8')
    assert 'const rows=own?(state.myRequests||[]):(state.publicTracked||[]);' in js
    assert "api('/api/my/requests')" in js
    assert 'Sign in for private Student/Alumni requests' in js
    # No admin-only data is fetched to populate guest/requester drill-down cards.
    start=js.index('function dashboardDetailPage(view)')
    end=js.index('function recentTracked()',start)
    assert '/api/admin/' not in js[start:end]
