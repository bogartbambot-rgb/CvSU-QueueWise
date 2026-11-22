# Upgrade Guide — v1.8 All-in-One Student, Alumni & Admin PWA

**One ZIP includes all requested features:** Registration, email verification, Student/Alumni role-specific dashboards, private My Requests, inline Date Needed calendar **inside the request form for both roles**, admin priority/arrival queue, approval before release, claimed log, SQLite, PWA, light/dark theme, and Railway deployment files.

## Update existing GitHub project on Windows (PowerShell)

1. **Back up the existing SQLite database before any upgrade.** Do not remove the running Railway `/data` volume.
2. Download and extract `CvSU_QueueWise_v1_8_All_In_One.zip` to `Downloads\QueueWise_v1_8`.
3. Copy project source into your existing Git repository while excluding `.env`, `.git`, `.venv`, and SQLite files:

```powershell
$source = "$env:USERPROFILE\Downloads\QueueWise_v1_8\CvSU_QueueWise_PWA"
$repo   = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret
cd "$repo"
git add .
git status
```

**Check `git status` carefully before commit**: no `.env`, secrets, SQLite files or real student information must be staged.

```powershell
git commit -m "Unify registration verification portals and inline Date Needed calendar"
git push origin main
```

If `git commit` says **nothing to commit**, double-check that you extracted the new ZIP and used the correct `$source` path; it may also mean the same changes are already committed. `robocopy` exit codes 1–7 do not necessarily mean failure. Git global config permission problems can be avoided using `git config --local user.name ...` and `git config --local user.email ...` inside the repo.

## Railway deployment

- Settings → Deploy → Start Command: `python run.py` (`railway.toml` already includes it).
- Root Directory: `/` **if** `run.py` is in the repository root.
- Variables:

```text
HOST=0.0.0.0
QUEUEWISE_DB_PATH=/data/queuewise.db
QUEUEWISE_HTTPS=1
QUEUEWISE_SECRET_KEY=<random 64-char secret>
QUEUEWISE_ADMIN_PASSWORD=<strong password for fresh database only>
RESEND_API_KEY=<your real Resend API key>
QUEUEWISE_EMAIL_FROM=QueueWise <verify@your-verified-domain.example>
QUEUEWISE_PUBLIC_URL=https://YOUR-ACTUAL-APP.up.railway.app
```

- Attach a **persistent Railway Volume** mounted at `/data` to the same service. Do not delete the existing volume after upgrades.
- The sender address must be authorized with your Resend account. A fictitious sender address or missing `RESEND_API_KEY` will **not** send real messages.
- Push to GitHub and inspect Railway deployment logs. A `git push` does not prove the service has successfully built and started.
- Visit the actual HTTPS domain; test new registration, email delivery, Student/Alumni private requests, and admin Date Needed visibility.
- Hard refresh with **Ctrl+Shift+R** or close/reopen the installed PWA if your old interface remains visible. A new service-worker cache version is included.

## Local Windows verification

```powershell
cd "$env:USERPROFILE\Downloads\QueueWise_v1_8\CvSU_QueueWise_PWA"
.\start_windows.bat
```

Open `http://127.0.0.1:8000/#login`. The demo registrar account for a freshly initialized local database is `admin` / `CvSU@2026Demo!`. On an existing database, use your existing admin password.

**Note on existing records:** Automatic schema upgrades preserve prior requests. Old anonymous requests cannot safely be assigned to newly registered accounts without authenticated ownership confirmation.
