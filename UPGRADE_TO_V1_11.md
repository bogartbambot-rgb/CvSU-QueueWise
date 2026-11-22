# QueueWise v1.11 — Upgrade, GitHub and Railway

This ZIP is the **complete application**, not just a patch. It is based on the Gmail API-enabled v1.10 source and preserves Student/Alumni registration, private requests, admin portal, CSRF, PWA, and SQLite.

## What changed

1. **Admin pickup scheduling:** an authorized registrar approves the request for preparation, then sets the actual pickup **date/time and optional instructions** in the Review dialog. A future appointment appears to the student/alumni as `Pickup Scheduled`; at the scheduled time it becomes `Ready for Release`. Staff confirm `Claimed` only after collection and never before the appointment.
2. **Required Date Needed reason:** students/alumni explain **why** they need the documents on that specific date (10–500 characters). Both the date and explanation appear in the registrar's Review window.
3. **Cancel Request:** the requester can cancel their own unscheduled, unclaimed request, with an optional reason. Cancellation is final; to correct a typo, submit a new request. Cancelled requests remain in arrival history but leave the active queue.
4. **Approve / Decline:** a staff member can approve for preparation or decline with a mandatory explanatory reason (10–500 characters). The requester sees the reason in **My Requests** and Notifications. Declined requests cannot be processed or claimed.
5. **Multiple documents in one submission:** choose one or more different document types; they share a single request ID, category, purpose, Date Needed, reason, and priority score. The database stores each chosen document in the `request_documents` table.
6. **University name removed from user-facing branding:** the UI, manifest and verification email identify the service as **QueueWise**. The source repo can retain its existing historical GitHub repository name.

The `requests` SQLite table is migrated non-destructively. Existing single-document requests are copied into `request_documents` automatically. **Back up the database before deploying.** Older requests may have no Date Needed explanation or new approval decision; the UI labels those fields as legacy rather than inventing values.

## Windows: safe upgrade to the existing Git repository

**Download** `QueueWise_v1_11_All_In_One.zip` and save it to your Windows `Downloads` folder.

```powershell
$zip = "$env:USERPROFILE\Downloads\QueueWise_v1_11_All_In_One.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_11"
$source = "$extract\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"

Expand-Archive -Path $zip -DestinationPath $extract -Force
Test-Path "$source\run.py"
Test-Path "$repo\.git"
```

**Both Test-Path commands must print `True`.** Stop if either is `False`: the path is wrong and Robocopy will not work.

```powershell
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-shm *.db-wal .session_secret
if ($LASTEXITCODE -ge 8) { throw "File copy failed. Check the Source and Destination paths." }

cd "$repo"
git add .
git status
```

Before committing, **verify no** `.env`, actual SQLite database, secrets, Gmail credentials, or personal records are staged.

```powershell
git commit -m "Add pickup scheduling, request decisions and multiple documents v1.11"
git push origin main
```

A `nothing to commit` message **after a successful copy** means Git detects no content differences; it is not proof that Railway is updated. Check `git log -1 --oneline` and Railway's latest Git commit. If Robocopy says `ERROR 3` (source not found), the files were never copied.

## Railway: no new variables required

Keep the existing **persistent SQLite Volume** mounted to `/data`, with `QUEUEWISE_DB_PATH=/data/queuewise.db`. Do not remove or recreate the volume. Keep a single service replica when writing to this SQLite file.

The Gmail email verification configuration from v1.10 is unchanged:

```text
QUEUEWISE_EMAIL_PROVIDER=gmail
GMAIL_CLIENT_ID=<your existing OAuth client ID>
GMAIL_CLIENT_SECRET=<your existing private client secret>
GMAIL_REFRESH_TOKEN=<your existing private refresh token>
GMAIL_SENDER_EMAIL=<the Gmail sender you authorized>
QUEUEWISE_PUBLIC_URL=https://<your-actual-railway-domain>
HOST=0.0.0.0
QUEUEWISE_DB_PATH=/data/queuewise.db
QUEUEWISE_HTTPS=1
```

Also keep the existing `QUEUEWISE_SECRET_KEY` and admin password setting. **Never commit credentials.** Railway start command remains `python run.py`. Wait for a deployment marked **Active** for the new v1.11 commit, then press `Ctrl + Shift + R` in the browser. The sidebar should display `v1.11`.

## Recommended tests after deploying

1. Sign in as a verified Student, open **Document Request → New Request** and check two documents. Fill Purpose, Date Needed and **Why do you need these documents on this date?** Confirm the single request ID and two items in My Requests.
2. Use a different Student/Alumni account to verify it cannot see or cancel someone else's request.
3. Sign in as registrar admin; select **Document Request → Review** for the request. Verify both documents and the requested-date explanation are visible. Approve the request, then schedule pickup in the future.
4. Sign in as the requester and verify `Pickup Scheduled` with the registrar-selected appointment and instructions. Admin should be unable to mark Claimed before that time.
5. Submit another request and **Decline** with a reason. Verify that only the submitting account sees the detailed decline reason.
6. Submit a third request and use **Cancel request** before release scheduling; verify it leaves the active queue but remains in your history.
7. Redeploy once and confirm documents, decisions and schedules still exist in the Railway SQLite volume.

## Test locally

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The Python automated suite passed **62 tests** during package creation. Live Gmail delivery, the Railway deployment, and an end-to-end browser session with your accounts still need to be verified on your machine.

**Academic demonstration only:** Date Needed is the requester's preferred deadline, not a guaranteed release date; registrar-set pickup time is the actual scheduled collection date. This system has no connection to a university identity or records service.
