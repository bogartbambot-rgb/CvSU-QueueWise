> **v1.11:** See [`UPGRADE_TO_V1_11.md`](UPGRADE_TO_V1_11.md) for the consolidated Student/Alumni, admin decision, cancellation, and pickup scheduling update. Keep the existing SQLite volume.

# QueueWise — GitHub + Railway deployment (SQLite)

**Purpose:** deploy this Python FastAPI + PWA prototype with SQLite persisted between restarts and deployments. **DB Browser for SQLite** is a local database viewer/editor, **not** the database host. Railway will run SQLite in the Python web service, stored in a persistent Railway **Volume**.

## 1. GitHub upload

Work **inside the folder containing `run.py` and `requirements.txt`**, not its parent folder. Create a **private, empty** GitHub repository named `CvSU-QueueWise`, with no generated README. In VS Code PowerShell:

```powershell
cd "C:\Users\Admin\Downloads\QueueWise_Railway\CvSU_QueueWise_PWA"   # adjust to your extracted location
git init
git branch -M main
git add .
git status
# Check that instance/, .env, .venv/, *.db, and session secrets are NOT staged.
git commit -m "QueueWise: Railway-ready PWA and SQLite persistence"
git remote add origin https://github.com/YOUR_USERNAME/CvSU-QueueWise.git
git push -u origin main
```

If Git does not know your identity, set:

```powershell
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
```

Sign in with Git Credential Manager / browser when prompted. Do not put passwords or `.db` files in GitHub.

## 2. Railway service

1. Open <https://railway.com> and create a project **Deploy from GitHub repo**. Authorize GitHub and select `CvSU-QueueWise`.
2. Check service root directory `/` if `run.py` is at repo root. If you uploaded the **parent** directory and the code is inside `CvSU_QueueWise_PWA`, set service **Root Directory** to `/CvSU_QueueWise_PWA` instead.
3. Under **Settings → Deploy → Start Command**, set **`python run.py`**. The code uses Railway's provided `PORT` variable. The repository now includes `railway.toml` with the same start command, which also works if the Railway dashboard setting is not configured.
4. Under **Variables**, add these keys (generate **your own secure unique secret and admin password**):

| Variable | Value |
|---|---|
| `HOST` | `0.0.0.0` |
| `QUEUEWISE_DB_PATH` | `/data/queuewise.db` |
| `QUEUEWISE_HTTPS` | `1` |
| `QUEUEWISE_SECRET_KEY` | random 64+ character secret, never commit |
| `QUEUEWISE_ADMIN_PASSWORD` | a unique strong password (only used when DB initialized for the first time) |

To generate the session secret in local PowerShell:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

**Never publish the generated secret or password.** You can also use Railway's secret variable generator if offered.

5. **Create a Volume and attach it to this same web service** (project canvas right-click → Add Volume / Command Palette), mount path: **`/data`**. This should be configured **before the first successful production startup**.
6. Redeploy after saving the variables, attached volume, and Start Command. The app initializes `/data/queuewise.db` on first startup.
7. **Settings → Networking → Public Networking → Generate Domain**, and visit the generated **HTTPS** address.
8. Log in at `https://YOUR-DOMAIN.up.railway.app/#login` using username `admin` and the password you set in `QUEUEWISE_ADMIN_PASSWORD` for the first database initialization. Change the password in **Profile → Security settings** after logging in.
9. Test: submit a test document request, sign in, update its status, restart/redeploy your service, and verify the request still exists. Then check that Chrome/Edge offers the PWA install option (on HTTPS).

## Email verification on live Railway

For real Student/Alumni verification emails through Gmail API, set `QUEUEWISE_EMAIL_PROVIDER=gmail`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER_EMAIL`, and `QUEUEWISE_PUBLIC_URL` (the actual public HTTPS Railway domain). Without the Gmail provider setting, four Gmail variables and a public URL, registration will return a configuration error; automated tests do not send real mail.

## 3. Very important SQLite notes

- `QUEUEWISE_DB_PATH=/data/queuewise.db` and a Railway Volume mounted at `/data` are a **matched pair**. Omitting either can make data ephemeral or cause filesystem errors.
- Do not add Railway Postgres or MySQL services: this project is **SQLite**.
- A fresh Railway deployment starts with **a fresh database**. Uploading your code to GitHub does **not** transfer `instance/queuewise.db` from your Windows PC. To migrate existing records, copy the SQLite database to the Railway volume separately (see Railway volume file-management docs). For SQLite in WAL mode, stop the local server and make a clean SQLite backup before copying; do not blindly upload only `.db` during writes.
- Use a **single instance/replica** with SQLite. Avoid scaling to multiple replicas or regions and avoid overlapping write deployments. Use volume backups. SQLite is well-suited for a small class demo, not automatically a production campus data platform.
- **Admin security:** `QUEUEWISE_ADMIN_PASSWORD` initializes the `admin` account only on first creation of a database. Changing it after that does not change an existing password. Use the in-app password-change functionality.
- Keep the GitHub repo private; `.gitignore` excludes local `instance/` and SQLite files. The Railway DB Browser application is **not** a remote client for your deployed file. You can inspect a downloaded copy (backed up safely) in DB Browser on your PC.
- Railway Free plan availability, capacity and billing vary. Consult <https://docs.railway.com/pricing/free-plan> and monitor usage to avoid service suspension.

## 4. Common errors

| Symptom | Likely cause / fix |
|---|---|
| Application Failed to Respond | Set `HOST=0.0.0.0`; Railway supplies `PORT`. |
| ModuleNotFoundError | `requirements.txt` not detected; check Railway Root Directory and build logs. |
| No start command found | Set **Start Command** to `python run.py`. |
| unable to open database file | Attach the Volume at `/data`; verify `QUEUEWISE_DB_PATH=/data/queuewise.db` and filesystem permissions. |
| Requests disappear after redeploy | Database is not writing on the attached persistent Volume or you deployed to a different environment. |
| Admin demo credentials fail | Use your custom `QUEUEWISE_ADMIN_PASSWORD` set before initial creation; existing DB passwords don't change through env. |
| Install PWA option missing | Use HTTPS and check manifest/service worker registration; browser install criteria vary. |

## 5. Updated source code later

From inside the same source folder:

```powershell
git add .
git commit -m "Improve QueueWise"
git push origin main
```

Railway can automatically deploy pushes to the connected branch. Check deployment logs and persistent requests after the update.

## Official Railway documentation

- <https://docs.railway.com/volumes>
- <https://docs.railway.com/volumes/backups>
- <https://docs.railway.com/deployments/start-command>
- <https://docs.railway.com/networking/public-networking>
- <https://docs.railway.com/pricing/free-plan>
