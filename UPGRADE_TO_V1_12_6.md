# QueueWise v1.12.6 — Registrar Monday–Thursday Office Days and 8 AM–5 PM Hours

Built on the complete v1.12.5 source code. Existing registration, Gmail verification, priority scoring, SQLite, PWA, original pickup, missed-pickup detection, and rescheduling remain in place.

## Office-hours rules (Asia/Manila)

| Flow | Allowed | Rejected |
| --- | --- | --- |
| Student/Alumni **Date Needed** | Monday, Tuesday, Wednesday, Thursday (today or later, within the 3-year request window) | Friday, Saturday, Sunday, past dates |
| Admin initial pickup | Monday–Thursday, **8:00 AM to before 5:00 PM**, future and within 365 days | Friday–Sunday, before 8 AM, **5 PM or later** |
| Admin pickup rescheduling | Exactly the same days and hours | Exactly the same rejections |
| Student/Alumni reschedule *request* | The requester may send a reason; registrar staff choose the new appointment | No Friday–Sunday or outside-hours pickup appointment can be assigned |
| Missed Pickup | Unclaimed pickup is marked Missed Pickup at 5 PM on its *scheduled* date (upon next relevant portal request) | No automatic claim or email is sent |

The Date Needed controls the requested day, **not the hour a user sends an online request**. For example, a Friday online submission is allowed if the selected Date Needed is Monday. No public-holiday schedule is implemented.

The request calendar visibly disables Friday–Sunday and shows an explanatory note. The admin date/time picker shows the office hours and gives a direct error when a closed day or invalid hour is entered. Both `/api/requests` and `/api/admin/requests/{public_id}/schedule` independently enforce the rules. The system stores appointment timestamps in Asia/Manila and keeps the original request ID and history on reschedule.

## Install the updated ZIP in the existing GitHub repository (Windows PowerShell)

1. Download `QueueWise_v1_12_6_Registrar_Office_Hours.zip` into Downloads and extract to `Downloads\QueueWise_v1_12_6`.
2. Do **not** recreate the Railway project or change the mounted `/data` SQLite volume.
3. Run these commands in PowerShell:

```powershell
$source = "$env:USERPROFILE\Downloads\QueueWise_v1_12_6\CvSU_QueueWise_PWA"
$repo   = "$env:USERPROFILE\Downloads\QueueWise_GitHub"
Test-Path "$source\run.py"  # must be True
Test-Path "$repo\.git"     # must be True
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret /R:2 /W:1
if ($LASTEXITCODE -ge 8) { throw "Robocopy failed" }
cd "$repo"
python -X utf8 -m pytest -q
```

4. Inspect the staged files to ensure secrets and databases are not included; then:

```powershell
git add .
git status
git commit -m "Update QueueWise v1.12.6 registrar office days and hours"
git push origin main
```

5. Check Railway **Deployments** and confirm your new commit is **ACTIVE** before testing the live site. `Ctrl + Shift + R` refreshes a browser tab; for installed PWAs, close and reopen the app to refresh the service worker.

## Manual test checklist

- Date Needed calendar: Monday–Thursday selectable; Friday–Sunday greyed out with closed-day note.
- Submit with a Friday/Saturday/Sunday date via the API: HTTP 400; valid weekday: accepted.
- Admin original pickup: Friday–Sunday rejected, 7:59 AM rejected, 8:00 AM accepted, 4:59 PM accepted, 5:00 PM rejected.
- Missed Pickup request: send reschedule reason, then admin still cannot schedule a new date on Friday–Sunday or outside working hours.
- Confirm existing registrar review, request tracking, account isolation and email verification are unaffected.

The automated test suite checks backend rules; live Gmail delivery and Railway deployment still need separate manual checks.
