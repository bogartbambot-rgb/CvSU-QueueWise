# QueueWise v1.12.2 — Compact Student/Alumni Calendar + Mobile Install App

## Changes

- **Date Needed calendar** is now compact (max-width 430px) inside **New Document Request** for both Student and Alumni. The day-grid is smaller, and the calendar shows only necessary week rows. The chosen date still fills the same request `deadline` field used by the registrar and priority algorithm. There is no separate Academic Calendar navigation.
- **Mobile PWA Install** actions remain visible on the public landing page under the login/register buttons and in the mobile header. If no native prompt is available, the Install action explains Android Chrome and iPhone Safari steps.
- Preserves previous v1.12 functionality: public login modal, Student/Alumni registration, Gmail verification, admin approval/decline, multiple documents, scheduling, cancellation, SQLite migration, and PWA offline shell.
- Cache and static asset URLs updated to v1.12.2 so phones receive the updated CSS/JS after deployment.

## Windows → GitHub → Railway update

1. Download `QueueWise_v1_12_2_Calendar_Mobile_Install_Fix.zip` into Downloads.
2. Open VS Code PowerShell and run:

```powershell
$zip = "$env:USERPROFILE\Downloads\QueueWise_v1_12_2_Calendar_Mobile_Install_Fix.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_12_2"
Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
$source = "$extract\CvSU_QueueWise_PWA"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"
Test-Path "$source\run.py"
Test-Path "$repo\.git"
```

3. Both checks must be `True`. Then:

```powershell
robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm .session_secret
if ($LASTEXITCODE -ge 8) { throw "Copy failed: robocopy exit code $LASTEXITCODE" }
cd "$repo"
git add .
git status
```

4. Verify that `.env`, SQLite files and secrets **are not staged**. Commit and push:

```powershell
git commit -m "Compact Student Alumni calendar and restore mobile PWA install v1.12.2"
git push origin main
```

5. In Railway > QueueWise > Deployments, wait for the **new commit** to show **Active**. Keep the SQLite volume mounted on `/data` and Gmail configuration variables unchanged. Avoid deleting database files.
6. Open the HTTPS site on your phone in Chrome (Android) or Safari (iOS). Refresh or close/reopen previously installed PWA to update cached assets. Test Student and Alumni > Document Request > New Request > Choose Date.

## Phone installation

- **Android Chrome:** Open external browser and tap the page Install action, or Chrome menu > Install app / Add to Home screen.
- **iPhone Safari:** Share > Add to Home Screen > Add (Open as Web App where offered).
- Browser native install prompts aren't guaranteed; if unavailable QueueWise shows platform instructions.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Note: Tests run locally using a test SQLite database. Real Gmail delivery and live Railway browser behavior should also be checked after deployment.
