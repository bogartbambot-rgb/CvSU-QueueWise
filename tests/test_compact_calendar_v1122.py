"""Regression checks for the compact Student/Alumni date-needed calendar."""
from fastapi.testclient import TestClient
from app import create_app


def test_compact_calendar_and_mobile_install_regression(tmp_path):
    with TestClient(create_app(str(tmp_path / "compact.db"), testing=True)) as client:
        html = client.get('/').text
        css = client.get('/static/css/auth.css').text
        js = client.get('/static/js/app.js').text
        marketing = client.get('/static/css/marketing.css').text
        sw = client.get('/sw.js').text
        assert 'v1.12.2' in html
        assert 'width:min(100%, 430px)' in css
        assert '.needed-day{box-sizing:border-box' in css
        assert 'height:40px' in css
        assert 'calendarCellCount = Math.ceil' in js
        assert 'function dateNeededWidget()' in js
        assert 'name="deadline"' in js
        assert 'id="calendarNavItem"' not in html
        assert 'class="qw-mobile-install" data-action="install"' in js
        assert '.qw-mobile-install{display:inline-flex' in marketing
        assert 'Android — Chrome' in html
        assert 'iPhone — Safari' in html
        assert 'queuewise-shell-v1122' in sw
