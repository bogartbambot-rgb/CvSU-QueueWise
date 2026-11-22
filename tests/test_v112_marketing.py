"""v1.12 user-facing public landing, login dialog, registration, and PWA branding."""
from fastapi.testclient import TestClient
from app import create_app

def test_marketing_shell_and_logo(tmp_path):
    with TestClient(create_app(str(tmp_path/'marketing.db'), testing=True)) as c:
        html=c.get('/').text
        js=c.get('/static/js/app.js').text
        css=c.get('/static/css/marketing.css')
        assert css.status_code == 200
        for marker in ('id="loginModal"','id="loginModalContent"','id="privacyModal"','/static/css/marketing.css?v=1.12','v1.12'):
            assert marker in html,marker
        for marker in ('function marketingLandingPage()', 'function loginModalMarkup()', 'function registerPage()', 'id="requesterLoginForm"', 'id="loginForm"','id="registerForm"', 'data-action="close-login"', 'data-auth-tab="staff"','data-register-role="Alumni"','name="consent"', 'data-action="toggle-auth-password"', 'function loginPage()', 'function loginModalMarkup()'):
            assert marker in js,marker
        for asset in ('/static/icons/queuewise-logo.png','/static/icons/icon-192.png','/static/icons/icon-512.png'):
            response=c.get(asset)
            assert response.status_code == 200 and response.content,asset
        assert 'queuewise-shell-v112' in c.get('/sw.js').text
        assert "url.pathname.startsWith('/api/')" in c.get('/sw.js').text
