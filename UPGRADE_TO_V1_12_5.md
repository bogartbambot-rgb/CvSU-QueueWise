# QueueWise v1.12.5 — Pickup Before 5:00 PM

This small update extends v1.12.4. It preserves the previous green UI, registrations, Gmail verification, SQLite records, approval workflow, missed-pickup detection and rescheduling.

## What's new

- Student/Alumni My Requests table shows: **Please claim your document(s) before 5:00 PM on the scheduled date. The Registrar's Office closes at 5:00 PM.**
- Admin request-review screen displays the same guidance when scheduling/rescheduling, and in scheduled pickup details.
- Scheduling API rejects an appointment at **5:00 PM or later** in Asia/Manila time (HTTP 400). This applies to first scheduling and rescheduling. Earlier times (e.g. 4:30 PM) are accepted, subject to existing status and date rules.
- **Missed Pickup** begins at **5:00 PM (Asia/Manila)** on the scheduled date if pickup was not confirmed; a 3 PM appointment can still be claimed at 4:30 PM. Before 5:00 PM it remains eligible for handover.
- In-app schedule and reschedule notifications include the reminder. This does not automatically send email, SMS or push notifications.
- No SQLite migration required. Existing scheduled dates remain unchanged.

## Update your existing VS Code / GitHub folder

1. Back up your current project and SQLite database.
2. Extract `QueueWise_v1_12_5_Pickup_Before_5PM.zip` to `Downloads\QueueWise_v1_12_5`.
3. Open PowerShell in your existing `QueueWise_GitHub` repository and run the commands below one line at a time:

```powershell
$source = "$env:USERPROFILE\Downloads\QueueWise_v1_12_5\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\QueueWise_GitHub"
Test-Path "$source\run.py"
Test-Path "$repo\.git"
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret /R:2 /W:1
if ($LASTEXITCODE -ge 8) { throw "File copy failed" }
cd "$repo"
git status
```

4. Inspect staged files for secrets, then:

```powershell
git add .
git status
git commit -m "Add registrar pickup closing-time reminder v1.12.5"
git push origin main
```

5. Confirm the latest commit is **ACTIVE** in your existing Railway service, keep volume `/data` attached, and test the pickup time limit and reminder on your live site. On phones with a previously installed PWA, fully close/reopen the app after deployment to refresh cached assets.

## Suggested test

1. Approve a test request in the Registrar portal.
2. Open **Review → Schedule document collection** and verify closing-time note.
3. Attempt `5:00 PM` → error; attempt `4:30 PM` on a future date → allowed.
4. Sign in as Student or Alumni and check **My Requests → Collection schedule** for the reminder.
5. Confirm same-day 4:59 PM is not missed, while 5:00 PM and later is missed if unclaimed (requires simulated clock or test). Confirm rescheduled appointments also reject 5:00 PM+.
