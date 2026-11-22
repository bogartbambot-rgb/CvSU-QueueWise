# CvSU QueueWise — Python + SQLite Progressive Web App

> **UPDATE v1.1 — NEW LOGIN / LOGOUT / PWA:** This version has a dedicated green two-column sign-in page, visible header/sidebar logout, and Install App controls. See [`UPGRADE_GUIDE.md`](UPGRADE_GUIDE.md) for exact Windows commands and steps to preserve your existing SQLite database.


> **Deploying to GitHub + Railway with persistent SQLite?** Read [`RAILWAY_DEPLOY_GUIDE.md`](RAILWAY_DEPLOY_GUIDE.md). This version supports the `QUEUEWISE_DB_PATH` environment variable so the database can be stored on a Railway Volume.

A complete, local, full-stack **academic prototype** for the project **“CvSU QueueWise: A Web-Based Document Request Processing System Using Priority Queue Algorithms”** (CPEN60, Group 1). Designed around the submitted proposal and updated for the requested interface.

> **Scope disclaimer:** This is a simulated project, not the official Cavite State University registrar service. The priority weights/categories are **group-proposed examples**, not official university policies. No payments, real student records, or university system connection are included.

## Demo registrar account

| Field | Value |
|---|---|
| **Username** | `admin` |
| **Password** | `CvSU@2026Demo!` |
| Access | Profile → **Registrar staff sign in** |

**IMPORTANT:** This account is created **only when the SQLite database is first initialized**. Change the password in **Profile → Security settings** before making the server accessible to anyone else. You can also set `QUEUEWISE_ADMIN_PASSWORD` *before first run* to customize the initial password. Changing that environment variable after the account exists **does not reset its password**.

## Requirements

- Windows 10/11, macOS, or Linux
- **Python 3.10 or newer** (`python --version`)
- Internet **for the first installation of Python packages** (application does not need external APIs)
- Optional: **DB Browser for SQLite** to examine the database visually
- A modern browser (Chrome, Edge, Firefox; Chrome/Edge supports PWA installation)

## Windows quick start (recommended)

1. Extract the ZIP into your Downloads folder (do not run from inside the ZIP).
2. Double-click **`start_windows.bat`**. The script creates `.venv`, installs dependencies, and starts the server.
3. Open **http://127.0.0.1:8000** in your browser.
4. Choose **Sign in** at the top right or **Registrar sign in** in the sidebar. Alternatively, open `http://127.0.0.1:8000/#login` and use the demo account above.
5. After signing in, go to **Document Request** and click **Load sample data** to populate 12 clearly labeled simulated records. This is optional; an empty database is normal initially.
6. Press **Ctrl+C** in the terminal to stop the app.

**Note:** If the `start_windows.bat` window closes immediately, launch it from Command Prompt to see error details. Do not run it from a compressed ZIP.

## Manual setup (PowerShell / Terminal)

```powershell
cd "C:\path\to\CvSU_QueueWise_PWA"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

If PowerShell blocks activation, simply use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe run.py` (no activation required).

For macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:8000`. To install as a PWA in Chrome/Edge, use the new **Install app** button on the page. If no native prompt appears, follow the popup instructions or use the browser address-bar install icon / browser menu. See `UPGRADE_GUIDE.md`. By default the server binds only to your own computer (127.0.0.1), not to a public network.

## Using DB Browser for SQLite

**DB Browser for SQLite is a database viewer/editor; the actual database engine is SQLite.** QueueWise automatically creates the file:

```text
CvSU_QueueWise_PWA/
└── instance/
    ├── queuewise.db       ← Open this in DB Browser for SQLite
    └── .session_secret   ← Keep this PRIVATE
```

1. Run `python run.py` at least once. The `instance` folder and SQLite DB are created automatically.
2. Open **DB Browser for SQLite** → **Open Database** → locate `instance/queuewise.db`.
3. Go to **Browse Data** to inspect these tables:
   - `users` — registrar login (`password_hash`, not plaintext)
   - `requests` — request data, generated public ID, priority score, status
   - `request_events` — status history, used for public tracking
   - `notifications` — in-app registrar activity
4. **Don't edit live records directly.** Stop the Python server before modifying the database in DB Browser. Reloading the browser after external edits will rebuild the demonstration data structures from SQLite.
5. The SQLite `.db-wal` and `.db-shm` files may appear while the app is running: this is normal SQLite WAL behavior.

**Never commit, email, or publish** `instance/queuewise.db` or `.session_secret` if it contains real information. The `.gitignore` excludes these files.

## Navigation and roles

The **left sidebar navigation** includes only:

- **Dashboard:** student/alumni request tracker and recent IDs; signed-in registrar queue metrics and upcoming requests.
- **Document Request:** submit a document request (guest); signed-in staff see requests, priority ranking, FIFO arrival history, status transitions, and optional sample data.
- **Notifications:** in-app request events (for public users, visible for locally saved reference IDs); registrar receives new-request/status events. **No email, SMS, or push notifications**.
- **Profile:** public guest information, registrar access shortcut, and staff password change. **Sign in / Log out** are now visible in the header and the sidebar utility area, too.

The **question-mark icon in the upper-right corner** opens a modal titled **“How the system works”** with separate **Student / Alumni** and **Registrar Staff** instructions. There is **no “How priority works” entry** in the sidebar.

The **moon/sun icon** switches between light and dark mode. The selection is saved per browser. On narrow screens the sidebar becomes a responsive hamburger menu.

## Core algorithms (implemented directly, not hidden by library containers)

The project follows the proposal's three distinct structures:

| Structure | File | Function |
|---|---|---|
| **Linear FIFO Queue (singly linked)** | `app/algorithms.py` → `ArrivalQueue` | Store **all** request IDs by original submission order; completed IDs stay in history. `enqueue`, `dequeue`, `front`, `is_empty`, `traverse` |
| **Nonlinear array-backed min-heap** | `app/algorithms.py` → `MinHeap` | Only **Pending** IDs are eligible; highest priority comes out first through a negative score. `insert`, `peek`, `extract_min`, `sift_up`, `sift_down`, `heapify` |
| **Separate-chaining hash table** | `app/algorithms.py` → `SeparateChainingHashTable` | Efficient request-ID lookup with collisions, `put`, `get`, `contains`, `update`, `resize` |

The **SQLite database** is a *separate durable storage layer*. It is not substituted for the three ADTs. For each request snapshot/operation, the server builds the FIFO queue, heap, and hash table from the database; changes to request statuses are saved atomically back to SQLite.

### Priority formula

The group-proposed weighted formula is:

```text
Priority Score = 0.50 U + 0.30 W + 0.20 C
```

- **U — deadline urgency (0–100):** `100 * max(0, 1 - max(0, days_left) / 30)`
- **W — waiting time (0–100):** `100 * min(1, max(0, days_waited) / 10)`
- **C — requester category:** Graduating = 100, Job Applicant = 60, Regular = 20.

Higher score = higher priority. The **min-heap key** is:

```text
(-priority_score, deadline, arrival_number, request_id)
```

So ties go to the **earlier deadline**, then **earlier arrival**, then **request ID**. Scores are refreshed and the heap is rebuilt before ranking and Process Next. **Process Next** marks the chosen Pending request **Processed** (as specified in the proposal). Staff may alternatively use the manual progression `Pending → Processing → Ready for Release → Processed` or select `Pending → Processed` directly.

The app uses the **Asia/Manila** date for submission, deadline validation, and scoring. Records persist on restart.

## Validation, privacy, and error handling

- Complete first and last name (2–60 characters); reject missing/one-word/numeric entries.
- Document type, requester category, and required-by deadline are validated again **on the server**.
- Deadline must be today or later and at most three years ahead.
- Request IDs are **automatic**, monotonically increasing, and unique: `REQ-0001`, `REQ-0002`, etc.
- SQLite transactions (`BEGIN IMMEDIATE`) prevent concurrent submissions from receiving conflicting IDs; failed operations roll back.
- Registrar processing endpoints require **authenticated staff sessions** and CSRF headers. Passwords use per-user salted PBKDF2-SHA256 hashes and constant-time verification.
- Guests with a reference ID see only **status, dates, and event history**, never requester names or registrar-only priority data.
- Completed requests remain searchable; empty queues return a clear message instead of crashing.
- JSON validation errors and unexpected exceptions return clean error messages. Frontend sanitizes server-returned text before rendering.
- PWA caches **only the app shell and an offline fallback**, not student or registrar API data. Submission and live tracking **require a connection**.

This is **not production-certified security**. For public deployment you would still need institutional approval, HTTPS, account management, monitoring/rate limiting, secure hosting, operational privacy compliance, and a full security audit.

## Automated tests

Install test-only dependencies and run:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

20 automated tests cover FIFO enqueue/dequeue, heap operations and stable ranking, separate-chaining hash lookup and resizing (200 records), exact priority-score examples from the proposal, time-based refresh, full-name validation, invalid deadlines, CSRF, staff-only endpoints, request submission/tracking, staff processing and status transitions, empty queues, PWA routes, notifications, password change, and **150 demo requests**.

## Folder structure

```text
CvSU_QueueWise_PWA/
├── app/
│   ├── __init__.py                 # FastAPI routes, validation, auth, staff API
│   ├── algorithms.py               # FIFO Queue, min-heap, hash table, scoring
│   ├── storage.py                  # SQLite schema, persistence, passwords
│   ├── templates/
│   │   ├── index.html              # Main app shell + PWA install guide
│   │   └── offline.html            # Offline fallback
│   └── static/
│       ├── css/styles.css          # Main responsive green UI + dark/light themes
│       ├── css/auth.css            # Dedicated two-column login and PWA controls
│       ├── js/app.js               # Page views, forms, session controls
│       ├── js/sw.js                # Service worker (offline app shell)
│       ├── icons/                  # 192px and 512px icons
│       └── manifest.webmanifest    # PWA manifest
├── tests/
│   ├── test_algorithms.py
│   ├── test_api.py
│   └── test_login_and_pwa.py
├── instance/                      # Created on first run; not in ZIP
├── start_windows.bat              # One-click Windows launcher
├── run.py                         # Local server
├── requirements.txt
├── requirements-dev.txt
├── TESTING_GUIDE.md                # Manual test matrix + complexity notes
├── .env.example
└── README.md
```

For a defense-ready manual test matrix and a note on the extra SQLite snapshot cost, see **`TESTING_GUIDE.md`**.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognized | Install Python 3.10+ and enable **Add python.exe to PATH**, then reopen the terminal. |
| `No module named fastapi` | Run `python -m pip install -r requirements.txt` using the same Python environment that launches `run.py`. |
| `No module named tzdata` / missing Manila timezone on Windows | Run `python -m pip install -r requirements.txt` (includes `tzdata`). |
| `Address already in use` | Stop the other app on port 8000, or launch with `PORT=8001` (PowerShell: `$env:PORT=8001; python run.py`). |
| Can't login | Use `admin` and `CvSU@2026Demo!` **only before the demo password is changed**. If you have changed it, use the new password. |
| Request ID not found | Verify the exact `REQ-0001` format and the correct SQLite database instance. |
| Requests missing after restart | Ensure you launched the **same extracted project folder** and didn't delete its `instance/queuewise.db`. |
| Submit says security token expired | Refresh the page so the session and CSRF token can be recreated. |
| Offline request submission fails | Reconnect to the server; the PWA supports offline shell display, not offline submission. |
| DB Browser shows database locked or out of date | Close any editing transaction in DB Browser, stop the app before editing, then reopen or refresh the table. |

---

### Proposal reference

Based on the uploaded *GROUP 1 - CPEN60 - FINAL PROJECT PROPOSAL.pdf*, especially pages 2–7 (scope, requirements, ADTs, score), pages 8–9 (workflow and pseudocode), and pages 11–12 (test plan and constraints). SQLite persistence, in-app notifications, modern PWA UI, theme support, and a staff profile are **user-requested extensions** to the original in-memory prototype. This implementation uses simulated records only.
