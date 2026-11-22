# CvSU QueueWise v1.1 — Login, Logout & PWA Update

## What changed

- Added a **full-page, responsive registrar staff sign-in screen** with a new original two-column layout and CvSU-inspired green palette. The left panel explains the service; the right panel holds the secure staff login form.
- Exposed **Sign in / Log out** in the app header and sidebar utility area. Authenticated staff can log out immediately without searching in Profile.
- Added **Install app** controls in the app header, sidebar, and sign-in page, with a readable manual-install guide when the browser does not expose a PWA install prompt.
- Preserved the left sidebar with just Dashboard, Document Request, Notifications, and Profile.
- Kept the upper-right question-mark **How the system works** dialog and the light/dark theme toggle.
- Updated the service worker to version **queuewise-shell-v4** and changed front-end assets to **v1.1 cache-busting URLs**, reducing the chance of stale interface files after upgrading.
- Kept Python FastAPI, SQLite persistence, staff sessions, and the same FIFO Queue, Min-Heap, Hash Table, validation, priority scoring, and admin account behavior.

## Start the updated project (PowerShell)

1. Stop the old server with `Ctrl+C` in its terminal.
2. Extract `CvSU_QueueWise_v1_1_Login_PWA_Fix.zip` into a new folder.
3. Open its nested `CvSU_QueueWise_PWA` folder in VS Code, or use commands below:

```powershell
cd "$env:USERPROFILE\Downloads\QueueWise_v1_1\CvSU_QueueWise_PWA"
.\start_windows.bat
```

Then open **http://127.0.0.1:8000/#login**.

The demo account for a newly created database:

```text
Username: admin
Password: CvSU@2026Demo!
```

If port 8000 is being used by another application, run:

```powershell
$env:PORT = "8001"
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:8001/#login** instead.

## Keep existing requests and admin password (optional)

When switching to a fresh extracted directory, the program will create a **new database**, so previous requests won't automatically appear. To retain your existing data:

1. Stop the old and new servers.
2. Copy **both** `instance/queuewise.db` and `instance/.session_secret` from your old `CvSU_QueueWise_PWA` directory into `instance/` under the **new** `CvSU_QueueWise_PWA` directory. Create `instance` if needed.
3. Don't overwrite the old database with a freshly created empty one. Keep a backup of the old `instance` directory first.
4. Start the new server. If you previously changed the admin password, continue using that password; the starter demo password is only assigned on initial database creation.

**Do not send your SQLite database or session secret to other people.** They may contain information that should remain private.

## How to install the PWA

1. Run the Python server and open QueueWise in **Chrome or Edge** at `http://127.0.0.1:8000` (or port 8001 if configured).
2. Click **Install app** on the page. If your browser offers an installation prompt, accept it.
3. If the prompt is not available, click the install icon in the address bar or use the browser menu's **Install** / **Apps → Install this site as an app** option when available.
4. The app can launch in its own window. Its cached shell supports an offline information page; **request submissions, login, notifications, and tracking still need the local Python server**.

PWA installation may not appear if your browser does not support it, the app is already installed, the origin is not trusted, or other installability criteria are not met. Access from another device using an ordinary `http://192.168...` LAN address is **not automatically a secure origin**; HTTPS is generally needed away from localhost.

After updating a previously installed version, close any open QueueWise app windows and hard-refresh the browser page (**Ctrl+Shift+R**) once so the new service worker and interface assets can load.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The included project has **20 automated checks**, including session lifecycle, protected routes, PWA resources, and the queue algorithms.
