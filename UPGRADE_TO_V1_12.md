# QueueWise v1.12 — Landing, Login Modal, Registration and Original Logo

This update starts from the complete v1.11 system. No database schema changes are made.

## Changes
- A modern public home / landing page opens at `/#dashboard` when signed out.
- `/#login` shows an accessible modal over the public landing page, with Student, Alumni and Registrar tabs.
- `/#register` is a dedicated registration page with Student/Alumni selection and email verification notice.
- A newly designed QueueWise logo appears in the public site, login modal and PWA icon.
- Light/dark mode, PWA install help, private requests, Gmail API verification, multiple documents, scheduling, cancellation, admin approval and SQLite persistence remain.
- Privacy notice and password-visibility toggles are accessible on the registration form.

## Windows / GitHub upgrade (PowerShell)
Download `QueueWise_v1_12_Landing_Login_Logo_All_In_One.zip` and save in Downloads.

```powershell
$zip = "$env:USERPROFILE\Downloads\QueueWise_v1_12_Landing_Login_Logo_All_In_One.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_12"
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
$source = "$extract\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
Test-Path "$source\run.py"
Test-Path "$repo\.git"
```
Both checks must return `True` before copying.

```powershell
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret
if ($LASTEXITCODE -ge 8) { throw "File copy failed" }
cd "$repo"
git add .
git status
```
Inspect staged changes to ensure no `.env`, secret credentials, OAuth tokens, local database, or private user data were included. Then:

```powershell
git commit -m "Update QueueWise v1.12 landing login registration and branding"
git push origin main
```

If nothing to commit, verify that the extracted `$source` points to v1.12 and that files actually copied.

## Railway
Monitor the new commit in Railway > CvSU-QueueWise > Deployments. Keep the persistent volume at `/data`, your existing `QUEUEWISE_DB_PATH=/data/queuewise.db`, HTTPS and Gmail API credentials. Do not remove or recreate the volume. A successful deploy does not establish that email delivery is working; test with a controlled email. After deploy, visit the live URL and hard-refresh if necessary.

## Manual acceptance checks
1. Signed-out landing page displays Login, Create an account, features, and the new logo.
2. Click Login: a modal opens; switch Student, Alumni, and Registrar. Close using × or Esc.
3. Click Register: dedicated form appears; switch roles; verify password visibility toggle and required consent.
4. Register using a test email and verify using the Gmail API delivery flow.
5. Sign in and check private Student/Alumni requests, multiple documents, cancellation, approval/decline, and scheduled pickup.
6. On mobile, forms remain readable, all buttons are reachable, and sidebar remains available when authenticated.
7. Install app uses the QueueWise icon and no private API responses are cached by the service worker.

**Reminder:** This is a school prototype; production security, identity verification and institutional policies require further work.
