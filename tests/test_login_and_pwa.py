"""Regression checks for the dedicated entry page and PWA delivery."""
from fastapi.testclient import TestClient
from app import create_app


def test_ui_delivers_login_logout_and_pwa_controls(tmp_path):
    with TestClient(create_app(str(tmp_path / 'entry.db'), testing=True)) as client:
        response = client.get('/')
        assert response.status_code == 200
        html = response.text
        for part in ('id="headerAuthButton"', 'id="sidebarAuthButton"', 'id="installButton"',
                     'id="sidebarInstallButton"', 'id="installModal"',
                     '/static/css/auth.css', 'How the system works'):
            assert part in html
        assert 'id="loginModal"' not in html  # Replaced with a real routed screen
        css = client.get('/static/css/auth.css')
        assert css.status_code == 200
        assert '.auth-landing' in css.text
        app = client.get('/static/js/app.js')
        assert app.status_code == 200
        for part in ("function loginPage()", "if (action==='logout')", "if (action==='login')",
                     "function installApp()", "'beforeinstallprompt'", "'appinstalled'",
                     "function updateInstallUI()"):
            assert part in app.text
        assert "navigate('login')" in app.text
        sw = client.get('/sw.js').text
        assert 'queuewise-shell-v4' in sw
        assert '/static/css/auth.css' in sw
        assert "url.pathname.startsWith('/api/')" in sw  # Never cache private API data
        manifest = client.get('/manifest.webmanifest').json()
        assert manifest['display'] == 'standalone'
        assert manifest['start_url'] == '/'
        assert len(manifest['icons']) >= 2


def test_login_logout_security_still_enforced(tmp_path):
    with TestClient(create_app(str(tmp_path / 'staff.db'), testing=True)) as client:
        token = client.get('/api/bootstrap').json()['csrf_token']
        assert client.get('/api/admin/requests').status_code == 401
        response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'CvSU@2026Demo!'},
                               headers={'X-CSRF-Token': token})
        assert response.status_code == 200
        assert client.get('/api/admin/requests').status_code == 200
        refreshed = client.get('/api/bootstrap').json()['csrf_token']
        assert client.post('/api/auth/logout', headers={'X-CSRF-Token': refreshed}).status_code == 200
        assert client.get('/api/admin/requests').status_code == 401
