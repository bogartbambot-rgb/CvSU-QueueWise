# v1.11 automated regression and manual acceptance checks

**Build result:** 62/62 pytest tests passed. `node --check` passed for the frontend code. Static JavaScript markup tests passed. Chromium navigation was unavailable in the build environment, so browser interaction must be checked on your deployed website.

New acceptance cases: multiple unique documents per submission (same transaction ID), required Date Needed explanation, owner-only cancellation, immutable cancellation and decline records, admin-required decline explanation, separate approve/decline decision, pickup date/time scheduling, rejection of past schedules, rejection of early pickup confirmation, minimal public tracking without private decline explanations, and migrations for existing SQLite records.

Run from the folder with `run.py`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Then follow the live acceptance steps in `UPGRADE_TO_V1_11.md`.

---

# QueueWise v1.9 — Functional and Regression Testing

Run from the project directory (not the parent folder):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**Package regression result: 50 tests passed.** Tests use temporary SQLite files and a simulated email outbox; no real email message is delivered during unit tests.

## Step-by-step acceptance checks

1. **Login / Registration landing:** Open `/#login`; confirm visible **Register as Student**, **Register as Alumni**, and separate **Registrar** login tab.
2. **Student registration:** Create an account. In a test environment, use the isolated test outbox; on Railway, configure the Gmail API OAuth sender credentials. Before email verification, requester login must be blocked. Open verification link to activate the account.
3. **Student landing/dashboard:** After login, see Student-specific greeting, Dashboard, Document Request, Notifications and Profile. **No Academic Calendar navigation** should appear.
4. **Student request:** Document Request → New Request. Fill document, category, purpose. Under **Date Needed**, click **Choose date**. The calendar opens **inside the form**. Select a future day, click **Use this date**. Form fields must remain filled. Submit and save the generated request ID.
5. **Alumni registration/dashboard:** Create and verify a separate Alumni account, then log in. The portal labels it Alumni, and the **same inline Date Needed calendar** is available in its New Request form.
6. **Account privacy:** As Student A, submit a request. Student B and Alumni A should see only their own My Requests. Manually calling `/api/my/requests` must still enforce account-specific filtering on the server.
7. **Admin date visibility:** Log in as admin → Document Request. Confirm the **Date Needed** column matches the date set by the student/alumni. Filter by requester type, and view FIFO/priority lists.
8. **Approval & claim:** A Pending request is not ready to claim. After staff processing, click **Approve for Release**. Only approved requests may be marked **Claimed**. Duplicate claims must be refused. Claim log records requester, document, timestamp and staff.
9. **Negative cases:** Blank required fields, invalid student number, weak password, duplicate email, expired/reused verification link, past Date Needed, unknown request ID, insufficient permissions, and invalid status transitions must produce errors without data corruption.
10. **UI/PWA:** Check sidebar on desktop/mobile, light/dark theme persistence, help `?` modal titled “How the system works,” Install App, and logout.
11. **Persistence:** Stop/restart server and confirm requests remain. On Railway, redeploy and confirm SQLite volume `/data` is still attached.

## Complexity reminders

| Structure / algorithm | Expected operation complexity |
|---|---|
| FIFO linked queue enqueue | O(1) |
| Heap insert / extract-min | O(log n) |
| Score refresh and bottom-up heapify | O(n) |
| Priority sorted view | O(n log n) |
| Separate-chaining hash lookup | O(1) average, O(N) worst case |

These complexities refer to the **ADT operations**, not the full HTTP request, which also reconstructs an in-memory snapshot from SQLite rows. Never describe the full API request as guaranteed O(1) solely because hash lookup averages O(1).


## v1.12 Browser UI smoke test

1. On the signed-out public landing, click **Sign in**: the login dialog must open over the landing page.
2. Change **Student / Alumni / Registrar** tabs in the dialog, then close with the × button or Esc. Tab selection changes the login form.
3. Click **Create an account**: dedicated registration form, not the login dialog. Switch Student/Alumni; the identification label should update.
4. Verify the password visibility control, required checkbox consent, Privacy Notice popup and light/dark mode.
5. Sign in using an authorized test account to verify protected dashboards, requests, multi-document submission and admin approval.
6. Check PWA install and both desktop/mobile layouts. Gmail API email delivery must be tested separately with configured Railway credentials.
