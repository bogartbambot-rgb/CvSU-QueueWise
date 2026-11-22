# Upgrade to QueueWise v1.9 — Clickable Dashboard Cards

This **complete source ZIP** includes all v1.8 features: Student/Alumni registration and role-specific login, email verification, request-private lists, Date Needed calendar inside the request form, admin approval and Claimed/Released records, SQLite storage, and Railway deployment configuration. v1.9 adds clickable dashboard cards with four distinct drill-down pages.

## New cards and pages

- **My Tracked Requests** → `/#tracked`: a list of reference IDs remembered in the browser; for signed-in Student/Alumni, a list of that account's own requests.
- **Active Requests** → `/#active`: pending, processing, awaiting approval and ready-for-release items.
- **Completed Requests** → `/#completed`: processed or claimed guest-tracked IDs; for signed-in accounts, only confirmed *Claimed* documents.
- **Online Portal / PWA** → `/#portal`: installation information and buttons for Install App, Sign in, Register or My Requests.
- Signed-in Student/Alumni **Ready to Collect** → `/#ready` (extra convenience, not a new sidebar item).

Each card is a keyboard-accessible button. Each detail page has a Back to Dashboard button. Public tracked IDs are not proof of account ownership; private Student/Alumni data is loaded from authenticated `/api/my/requests` endpoints. No SQLite schema migration is required for v1.9.

## Upload safely to your existing GitHub repository

1. **Back up your local `instance/queuewise.db` and leave your Railway volume attached.**
2. Extract `CvSU_QueueWise_v1_9_Clickable_Dashboard_All_In_One.zip` to `Downloads\QueueWise_v1_9`.
3. Run in PowerShell:

```powershell
$src = "$env:USERPROFILE\Downloads\QueueWise_v1_9\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
Test-Path "$src\run.py"     # Must return True
Test-Path "$repo\.git"      # Must return True
robocopy "$src" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret
cd "$repo"
git add .
git status
```

Inspect the staged changes for secrets, `.env`, SQLite databases, and personal data. Once safe:

```powershell
git commit -m "Add clickable QueueWise dashboard cards and detail pages"
git push origin main
```

If you see `nothing to commit`, verify the source path and copied file changes. The `git push` does not confirm a successful Railway deployment. On Railway, check the **latest build and deploy logs**, and confirm the deployed commit matches the new GitHub commit.

## Railway configuration retained

- Start Command: `python run.py`; service Root Directory `/` if `run.py` is in repo root.
- SQLite persistent Volume: `/data`; `QUEUEWISE_DB_PATH=/data/queuewise.db`.
- Real email verification needs a configured Resend account and valid `RESEND_API_KEY`, `QUEUEWISE_EMAIL_FROM`, and `QUEUEWISE_PUBLIC_URL`.
- Keep existing `QUEUEWISE_SECRET_KEY` and your attached Railway volume during upgrades.
- After deployment, hard-refresh (`Ctrl+Shift+R`) and check the sidebar version is `v1.9`. Installed PWA users may need to close and reopen the app.

## Local verification

```powershell
.\start_windows.bat
```

Visit `http://127.0.0.1:8000/#dashboard`, click each of the four guest cards, verify the details page/Back button, then sign in and test private requests. No real email will be delivered without email provider configuration.
