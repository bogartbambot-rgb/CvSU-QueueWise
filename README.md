# QueueWise v1.12 — All-in-One Full-Stack PWA

This ZIP includes the entire previous v1.11 QueueWise project **plus** a brand-new public landing page, a real login popup over that page, a separate Student/Alumni registration page, and the custom QueueWise logo and PWA icons.

**New v1.12 pages:** `/#dashboard` (signed-out landing), `/#login` (login modal), `/#register` (registration page), and `/#verify-email` (existing verification screen). Once signed in, the registered role's protected dashboard, requests, notifications, profile, admin approvals, multi-document requests and pickup scheduling remain.

See **UPGRADE_TO_V1_12.md** for exact Windows, GitHub and Railway instructions. Keep your existing `/data` Railway volume and Gmail API variables. This is a school prototype, not an official registrar service.

---

# QueueWise v1.11 — All-in-One Document Request PWA

**Python FastAPI · SQLite (DB Browser compatible) · Gmail API email verification · Student/Alumni portals · Registrar portal · Installable PWA**

This is a demonstration system using simulated document requests, not an official university service. The source preserves the educational FIFO Queue, binary min-heap and separate-chaining hash table with the group-proposed priority score **PS = 0.50U + 0.30W + 0.20C**. The scoring policy is not an institutional policy.

## Functional roles and workflows

**Student and Alumni:** Create an account → verify email → sign in to the correct role-specific dashboard → Document Request → New Request. Choose **multiple documents under one request ID**, purpose, requester category, preferred Date Needed with the embedded calendar, and a **required explanation** for that date. The account sees *only its own* requests, decision details, appointment, notifications and cancellation controls.

**Registrar:** See all submissions and priority ranking → open **Review** → examine requested documents, date and explanation → **Approve request** for preparation or **Decline request** with a required reason. When approved documents are prepared, choose **Schedule pickup** with a specific date/time and optional instructions. The requester sees `Pickup Scheduled` until the appointment, then `Ready for Release`. The registrar records **Claimed** only when the documents are actually handed over. Declined, cancelled and claimed requests are final and remain auditable/searchable.

**Cancel / correction:** Student/Alumni can cancel their own request before release is scheduled. They can then make a corrected new submission. Cancellation is not an in-place edit and preserves the original request in history.

**Multiple documents:** Each document type is stored in a `request_documents` SQLite child table; a submission uses one generated transaction ID and one priority score. Existing single-document records migrate automatically without losing IDs or status history.

## Run on Windows

Extract the archive, open the included `CvSU_QueueWise_PWA` folder and double-click `start_windows.bat`. Or from VS Code PowerShell inside that folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open <http://127.0.0.1:8000>. The fresh local test database starts with registrar account **`admin`** and demo password **`CvSU@2026Demo!`**; change the password under Profile. Use a strong unique password for public deployment. A Railway `QUEUEWISE_ADMIN_PASSWORD` variable does **not** overwrite an admin password already saved in SQLite.

## Email verification

In Railway use the v1.10 Gmail configuration: `QUEUEWISE_EMAIL_PROVIDER=gmail`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL`, and `QUEUEWISE_PUBLIC_URL` pointing at the deployed HTTPS website. A sender must be authorized with Gmail `gmail.send`. Never commit OAuth credentials. Accounts remain unverified until the 24-hour one-time link is confirmed. OAuth testing-mode refresh tokens may expire after 7 days.

## SQLite and Railway

SQLite is the database; **DB Browser for SQLite** is a local editor/viewer. Locally it lives in `instance/queuewise.db`. On Railway, create a **persistent Volume** mounted to `/data` and set `QUEUEWISE_DB_PATH=/data/queuewise.db`. Keep a single replica; do not delete the volume during an upgrade. The included `railway.toml` starts `python run.py` and uses the hosting platform's `PORT`.

New nullable columns and the document-items table are created automatically when the app starts with an older v1.10 database. Back up existing SQLite before upgrading. Existing anonymous requests are **not** attached to new portal accounts by name or ID alone.

**Upgrade instructions with exact Windows copy + Git commands:** [`UPGRADE_TO_V1_11.md`](UPGRADE_TO_V1_11.md)

**Railway setup:** [`RAILWAY_DEPLOY_GUIDE.md`](RAILWAY_DEPLOY_GUIDE.md)

## Automated tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**62/62 tests passed** in the build environment. The tests cover validation, permissions, multi-document atomic requests, decline reasons, cancellation, schedule-not-before-claim enforcement, old database migration and existing Gmail/PWA/priority features. Browser-level navigation and live Gmail/Railway delivery should be tested after deployment; they are not proven by the automated suite.
