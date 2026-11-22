# CvSU QueueWise v1.10 — Gmail API Email Verification v1.9 — All-in-One Full-Stack PWA

**Python FastAPI · SQLite · Student / Alumni · Registrar Admin · Email verification · Inline Date Needed Calendar**

An academic demonstration prototype for **CvSU QueueWise: A Web-Based Document Request Processing System Using Priority Queue Algorithms** (CPEN60). **Not an official CvSU registrar website.** All test documents, people and priorities should be simulated.

## What is included in this one project?

| Portal | Features |
|---|---|
| Guest / Login | Professional green CvSU-inspired two-column landing/login page, **Register as Student**, **Register as Alumni**, staff login tab, `?` **How the system works**, installable PWA, dark/light theme |
| Student | Account registration, email verification, own verified-login dashboard, **My Requests** only, notifications, profile and logout |
| Alumni | Same professional register/login flow, **separate Alumni dashboard**, **My Requests** only, notifications, profile and logout |
| Both requester portals | **Document Request → New Request** includes an **inline interactive Date Needed calendar** with previous/next month, Today, date selection, and **Use this date**; it does **not** navigate to another page |
| Registrar Admin | View every Student/Alumni request, **Date Needed column**, FIFO arrival order, min-heap priority, explicit **Approve for Release**, **Mark as Claimed**, and Claimed/Released log with timestamp and staff |
| Backend | Server-side role authorization, account-linked private requests, CSRF checks, password hashing, expiring email tokens, validation, SQLite migrations and persistence |
| Algorithm | FIFO Queue, min-heap with `(-PS, deadline, arrival, ID)`, separate-chaining hash table and weighted priority **PS = 0.50U + 0.30W + 0.20C** |

The **Date Needed calendar is now inside the New Request form** for Student **and** Alumni, not an Academic Calendar sidebar page. Its chosen date is saved in SQLite as the `requests.deadline` column (for compatibility with earlier versions) and shown as **Date Needed** to the registrar. This date influences priority score; it **does not promise pickup on that date**. Staff approval is required before the document can be marked Ready for Release and then Claimed on actual handover.

## Windows startup

1. Extract this ZIP so that you can see the `CvSU_QueueWise_PWA` folder.
2. Open that folder in VS Code or File Explorer.
3. Double-click `start_windows.bat`. It prepares a Python virtual environment and installs dependencies on first run.
4. Open **http://127.0.0.1:8000**. Go to **Sign in**, or directly `http://127.0.0.1:8000/#login`.

Manual alternative in VS Code PowerShell (run inside the folder containing `run.py`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

If port 8000 is already occupied, close the previous server or run `python -m uvicorn app:app --host 127.0.0.1 --port 8001` (using the virtual environment's Python).

**Demo registrar account (local fresh database only):** username `admin`, password `CvSU@2026Demo!`. Change it under **Profile → Security settings**. For Railway, provide a custom strong initial password through `QUEUEWISE_ADMIN_PASSWORD` **before the SQLite file is created**. Changing the environment variable later does not overwrite the password of an existing admin.

## Student / Alumni account registration and verification

1. On the login page, click **Register as Student** or **Register as Alumni**.
2. Enter full name, student/former student number, email, password and confirmation.
3. The account is **Unverified** until the user opens the **24-hour email verification link** and selects Verify.
4. Sign in through the matching **Student** or **Alumni** login tab. The account's private landing/dashboard opens automatically.
5. Select **Document Request → New Request**. Choose document type, category, purpose; click **Choose date**, pick a valid date **within the same form**, click **Use this date**, then **Submit document request**.
6. Only that account's own requests appear under **My Requests** and own notifications. The staff dashboard can see every request and the selected date.
7. The registrar processes the request, explicitly approves it for release, and records **Claimed** after document pickup. Requests remain searchable after processing.

**Real email sending requires setup:** Gmail API is now supported. Configure `QUEUEWISE_EMAIL_PROVIDER=gmail`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL`, and `QUEUEWISE_PUBLIC_URL` with the actual public **HTTPS** Railway URL. Optional Resend sending remains supported when explicitly selected and properly configured. Without this configuration, new registrations return a clear error instead of pretending an email was sent. Automated tests use an isolated simulated email outbox; they do **not** send live messages. The account verification step does not verify a person's actual CvSU student/alumni identity.

## SQLite and Railway

- The SQLite database is created at `instance/queuewise.db` by default, and can be opened locally with **DB Browser for SQLite**. DB Browser is an editor, not a database host.
- For Railway, attach a **persistent Volume** at `/data`, and set `QUEUEWISE_DB_PATH=/data/queuewise.db`. Keep the same volume connected across deployments. Use a single web-service replica with this SQLite file.
- Set Railway Start Command to `python run.py` or use the included `railway.toml`. `HOST=0.0.0.0`; Railway provides `PORT`.
- Set `QUEUEWISE_HTTPS=1`, a random `QUEUEWISE_SECRET_KEY`, a strong `QUEUEWISE_ADMIN_PASSWORD`, and the Gmail API variables listed above.
- See **[`RAILWAY_DEPLOY_GUIDE.md`](RAILWAY_DEPLOY_GUIDE.md)** and **[`UPGRADE_TO_V1_10.md`](UPGRADE_TO_V1_10.md)** for complete commands and safe migration instructions.

**Existing SQLite data:** The app automatically migrates earlier schemas without wiping request history. Make a backup before upgrading. Older anonymous requests are not automatically attached to a newly registered student/alumni account; doing that without verifying ownership would be unsafe.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**56 automated tests passed** for v1.10 at package creation, covering data structures, status transitions, admin permission, registration, email verification, account isolation, SQLite migrations, date validation, and admin visibility of Date Needed. A separate browser-rendered frontend smoke check verified inline calendar date selection with Student and Alumni UI and retained form fields. **Actual email delivery and Railway deployment still require your own provider credentials and live deployment checks.**

## Key design limitations

This is an academic prototype. It does not handle real issuance, document uploads, payments, identity checks with CvSU, nor guaranteed processing dates. The formula is a **group-proposed weighted-score policy**, not an official registrar priority policy. The PWA caches static assets/offline help only—new requests and status changes require the Python server to be online.
