# QueueWise v1.12.3 — Student & Alumni Registration Name Fix

This is a complete source-code package built from **v1.12.2**. It fixes rejection of otherwise valid registration names and keeps prior functions (Gmail verification, admin processing, multi-document requests, calendar, mobile PWA, SQLite, FIFO/heap/hash implementations).

## What's changed

- **Student and Alumni registration:** three separate inputs: **First name** (required), **Middle name** (optional), and **Last name** (required), responsive on desktop and mobile.
- **Validation:** middle initial `M.`, multiple first names (`Mary Jane`), multi-part surnames (`Dela Cruz`), accented names, and hyphen/apostrophe names are accepted. Empty required names, numeric names and markup are rejected with a clear message.
- **Profile and requests:** the backend assembles and retains the complete display name in `full_name`. Request submission validation now accepts a legitimate middle initial too.
- **SQLite migration:** add nullable `first_name`, `middle_name`, `last_name` columns to `portal_users` without altering or deleting older accounts, authentication data, request records, or verification tokens. Older accounts continue using their existing `full_name`.
- **Compatibility:** older integrations sending `full_name` continue to work; the updated interface sends the three separate fields instead.
- **PWA:** cache version advanced to `queuewise-shell-v1123` so the new registration form can refresh after deployment.

## Updating a Windows GitHub checkout

**Before copying:** back up the local SQLite database if you have one. Do **not** upload database files, `.env`, or OAuth tokens to GitHub.

Save `QueueWise_v1_12_3_Registration_Name_Fix.zip` to your Windows Downloads folder, then use PowerShell:

```powershell
$zip = "$env:USERPROFILE\Downloads\QueueWise_v1_12_3_Registration_Name_Fix.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_12_3"
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

$source = "$extract\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
Test-Path "$source\run.py"
Test-Path "$repo\.git"
```

**Only continue if both checks show `True`.** Then:

```powershell
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret
if ($LASTEXITCODE -ge 8) { throw "Source copy failed — check the path above" }

cd "$repo"
git add .
git status
```

Review staged changes and ensure no personal records or secrets were included. Then:

```powershell
git commit -m "Fix Student Alumni first middle last name registration v1.12.3"
git push origin main
```

On Railway, open your **QueueWise → Deployments**, confirm the new commit becomes **Active**, and do not remove your volume mounted to `/data`. No new Railway variables are required. Refresh the web app on desktop and mobile; try a private/incognito tab if an older service worker persists.

## Manual acceptance checklist

1. Open Register → Student. Enter `Mary Jane` / `A.` / `Dela Cruz` and valid email/password. Registration should lead to email verification (with the configured Gmail sender).
2. Repeat for Alumni with Middle name left blank. It should be optional.
3. Verify and sign in; the displayed full name must be assembled correctly.
4. Submit a document request. The name containing `A.` must be accepted, and the request must appear only for that account.
5. Try missing first/last name and numeric inputs; registration should be rejected without creating a partial record.
6. Sign in to an account created before this update. Its name and existing requests should still be available.

**Note:** Email verification still requires valid Gmail API credentials and an active sender token in Railway; this update does not bypass email verification or fix provider-side sending failures.

## Automated tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**81 automated tests passed** in the build environment. Live Railway and actual email delivery still need your deployment-side check.
