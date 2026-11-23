# QueueWise v1.12.4 — Missed Pickup and Rescheduling

## Current issue addressed
Previous versions displayed **Ready for Release** after an appointment expired. They did not classify a missed pickup or permit rescheduling an already scheduled release.

## Exact rule
- A pickup is **not** automatically marked missed the moment its scheduled hour passes. It becomes **Missed Pickup** only when the *entire scheduled date* has passed in the **Asia/Manila** time zone and the registrar has not confirmed a physical handover.
- **Missed Pickup** does NOT mean Declined, Cancelled, Claimed or Processed. The same request, documents, student/alumni and priority history remain in SQLite.
- On the **next relevant Student/Alumni or registrar API visit** (not through a continuously running scheduler), QueueWise records the Missed Pickup event and an **in-app notification once**. An active browser refresh may be required. This change **does not send proactive emails, push notifications or timed notifications while everyone is offline**.
- Students and alumni can choose **Request new pickup date** from **My Requests** and must enter a 10–500 character reason; they cannot choose/approve a new schedule themselves.
- The request changes to **Reschedule Requested**. The registrar can see the reason, review the request, and schedule a new future pickup appointment in **Document Request → Review**.
- After a new schedule, the portal displays **Pickup Scheduled** with updated time and any pickup instructions; the old date and reason remain in the activity event log. Registrar must explicitly confirm *Claimed* after actual handover. For a missed day, the admin cannot use Claim until a new date is scheduled.
- The registrar may also reschedule an already **Missed Pickup** request directly without a user rescheduling request; no duplicate document request is necessary.
- Existing FIFO arrival IDs, heap scheduling, hash lookup, student/alumni access controls, Gmail verification and SQLite database stay intact.

## Install in your existing GitHub repository (Windows PowerShell)

1. Save **QueueWise_v1_12_4_Missed_Pickup_Reschedule.zip** to your Downloads folder.
2. Run:

```powershell
$zip = "$env:USERPROFILE\Downloads\QueueWise_v1_12_4_Missed_Pickup_Reschedule.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_12_4"
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
$source = "$extract\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
Test-Path "$source\run.py"
Test-Path "$repo\.git"
```

Both checks must be **True**. Do not proceed if either returns False.

```powershell
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-shm *.db-wal .session_secret
if ($LASTEXITCODE -ge 8) { throw 'File copy failed' }
cd "$repo"
git add .
git status
```

Review staged files. **Never commit** `.env`, token files, secrets, PWA user data, or `*.db` files. Then:

```powershell
git commit -m "Add QueueWise v1.12.4 missed pickup and rescheduling"
git push origin main
```

In Railway, confirm the deployment is **Active** with this exact new commit; **keep the SQLite volume on `/data`**. Database migration is additive and preserves old requests. Make a database backup before deploying. Refresh browser `Ctrl + Shift + R` and reopen an installed PWA for the new files to load.

## Test plan

1. Create a Student or Alumni test request and approve + schedule pickup as registrar.
2. On the original appointment date, before midnight Manila time, the request should **not** be Missed Pickup solely because the scheduled time has passed.
3. For safe testing, set up a test database and adjust the scheduled pickup date to yesterday (never edit production data solely to test). Refresh My Requests. Status becomes **Missed Pickup**, with one in-app notification.
4. Click **Request new pickup date**, enter an explanation, then submit. Status becomes **Reschedule Requested**; repeating should be rejected.
5. Log in as registrar. Open **Document Request → Review**, read the explanation and set a new future pickup date/time.
6. Student/Alumni sees **Pickup Scheduled** with new details. Old events remain searchable in the notifications/activity history.
7. Claim on a missed appointment before rescheduling must fail (409). Claim after a new scheduled time and actual handover is permitted only to registrar.
8. Attempt to reschedule another account's request: 404. Attempt to alter a Claimed, Cancelled, or Declined request: 409.

### Technical references
- `app/storage.py`: additive SQLite migrations for `missed_at`, `reschedule_requested_at`, `reschedule_reason`, `reschedule_count`.
- `app/__init__.py`: `missed_pickup`, `sync_missed_pickups`, requester reschedule and registrar schedule endpoints.
- `app/static/js/app.js`: new My Requests action, reschedule modal handler and admin status filter.
- `tests/test_missed_pickup_v1124.py`: deadline boundary, duplicate alert, ownership, reschedule and claim checks.

## Operational scope
This is an academic prototype. It does not automatically terminate missed requests or guarantee document retention for a specified number of days. Your registrar team should separately define collection/grace-period and unclaimed-document disposal policies if used operationally.
