"""Check mobile install visibility and cross-platform installation guidance."""
from pathlib import Path
from fastapi.testclient import TestClient
from app import create_app


def test_mobile_install_visible_and_instructions(tmp_path):
    with TestClient(create_app(str(tmp_path / "pwa.db"), testing=True)) as c:
        css = c.get('/static/css/marketing.css').text
        js = c.get('/static/js/app.js').text
        html = c.get('/').text
        assert '.qw-marketing-tools .qw-install{display:none}' not in css
        assert '.qw-mobile-install{display:inline-flex' in css
        assert 'class="qw-mobile-install" data-action="install"' in js
        assert 'Android — Chrome' in html and 'iPhone — Safari' in html
        assert 'Add to Home Screen' in html and 'Install app' in html
        assert 'apple-touch-icon.png' in html
        assert c.get('/static/icons/apple-touch-icon.png').status_code == 200
        assert 'queuewise-shell-v1122' in c.get('/sw.js').text
