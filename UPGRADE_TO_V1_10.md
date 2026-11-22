# CvSU QueueWise v1.10 — Gmail API verification deployment guide

This version is based on v1.9 and adds Gmail API **send-only** verification email delivery. It retains Student/Alumni registration, role-specific login and dashboards, admin approval before release, claimed-record history, private My Requests, interactive Date Needed calendar within the request form, and PWA functionality. The SQLite schema and persistent volume path are unchanged.

## 1. Google Cloud checklist

In your `CvSU-QueueWise` Google Cloud project:

1. Enable **Gmail API**.
2. Open **Google Auth Platform → Audience** and add the Gmail *sender* address as a test user while the OAuth app is in Testing mode. Student/alumni recipients do **not** need to be test users.
3. Create a **Web application** OAuth client (or use your existing one) with authorized redirect URI `https://developers.google.com/oauthplayground` if you authorize through the OAuth Playground.
4. Configure **Data Access** with `https://www.googleapis.com/auth/gmail.send` (send-only scope).
5. In [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/), choose **Use your own OAuth credentials**, paste your client ID and secret, select the `gmail.send` scope, authorize **the Gmail account that will send emails**, and exchange the authorization code for a **refresh token**. Keep Client Secret and Refresh Token private.

**Important:** A refresh token from an External OAuth app in **Testing** mode generally expires after 7 days when Gmail scopes are used. Google may require app verification for broader production OAuth use. For a short class demonstration, reauthorization may be necessary after expiry. Do not promise unlimited free production email sending.

## 2. Extract & copy the ZIP (Windows PowerShell)

Download `CvSU_QueueWise_v1_10_Gmail_API_Ready.zip` into `Downloads` and run:

```powershell
$zip = "$env:USERPROFILE\Downloads\CvSU_QueueWise_v1_10_Gmail_API_Ready.zip"
$extract = "$env:USERPROFILE\Downloads\QueueWise_v1_10"
$repo = "$env:USERPROFILE\Downloads\CvSU_QueueWise_FullStack\CvSU_QueueWise_PWA"

if (-not (Test-Path $zip)) { throw "ZIP not found: $zip" }
Expand-Archive -Path $zip -DestinationPath $extract -Force
$source = Join-Path $extract "CvSU_QueueWise_PWA"
if (-not (Test-Path (Join-Path $source "run.py"))) { throw "Wrong extracted source location: $source" }
if (-not (Test-Path (Join-Path $repo ".git"))) { throw "Not a Git repo: $repo" }

robocopy "$source" "$repo" /E /XD .git .venv instance __pycache__ .pytest_cache /XF .env *.db *.db-wal *.db-shm *.sqlite *.sqlite3 .session_secret
if ($LASTEXITCODE -ge 8) { throw "Robocopy failed (exit code $LASTEXITCODE)" }
cd "$repo"
git add .
git status
```

Review the files staged by `git status`; there should be **no `.env`, SQLite databases, secrets, or refresh tokens**. Then:

```powershell
git commit -m "Add Gmail API email verification to QueueWise v1.10"
git push origin main
```

If Git says `nothing to commit`, verify that the **ZIP was downloaded and copied**, using the source `Test-Path` check above. Do not delete the existing SQLite volume. If Git reports `Permission denied` on global Git config, set your name and email with `git config --local` inside the repo instead.

## 3. Railway service variables

Go to Railway → QueueWise service → **Variables**. Use the exact names below:

| Name | Value |
| --- | --- |
| `QUEUEWISE_EMAIL_PROVIDER` | `gmail` |
| `GMAIL_CLIENT_ID` | From your Google Cloud OAuth client |
| `GMAIL_CLIENT_SECRET` | OAuth Client Secret (private) |
| `GMAIL_REFRESH_TOKEN` | OAuth Playground Refresh Token (private) |
| `GMAIL_SENDER_EMAIL` | Same Gmail address you authorized |
| `QUEUEWISE_PUBLIC_URL` | `https://cvsu-queuewise-production.up.railway.app` (confirm it still matches your deployed domain) |
| `HOST` | `0.0.0.0` |
| `QUEUEWISE_DB_PATH` | `/data/queuewise.db` |
| `QUEUEWISE_HTTPS` | `1` |
| `QUEUEWISE_SECRET_KEY` | Keep the existing secure value |
| `QUEUEWISE_ADMIN_PASSWORD` | Keep the existing value; it doesn't reset a previously created admin account |

With `QUEUEWISE_EMAIL_PROVIDER=gmail`, **`RESEND_API_KEY` and `QUEUEWISE_EMAIL_FROM` are not needed**. Delete the accidental variable names `queuewise-example` and `queuewise-example.com` if still present. Never reveal secrets in screenshots or GitHub commits.

Save/Apply the Variables, let Railway deploy the new `main` commit, confirm **Active** and check logs. If the new build fails, the previous Active deployment may remain online but won't have the Gmail integration.

## 4. Test end-to-end

1. In the live QueueWise URL, open Sign in → Register, choose Student or Alumni, and use a **test account you control**.
2. Submit registration. Expect an email message, not the previous `Email verification is not configured` error.
3. Check Inbox, Spam and Promotions. Click the emailed verification link.
4. Click **Verify Email** on the page; then sign in. The dashboard should show only this account's requests.
5. As registrar, confirm the document appears with **Date Needed**, and test approval → Ready for Release → Claimed.

If a previous registration attempt created an unverified account, use **Resend verification email** instead of re-registering with the same student number/email.

## 5. Troubleshooting

- **`Email verification is not configured`**: Check that the new v1.10 commit is Active, all Gmail variables are nonempty, `QUEUEWISE_EMAIL_PROVIDER=gmail`, and the public URL starts with `https://`.
- **`Gmail authorization was rejected or expired`**: Verify the sender account matches your OAuth authorization, your `GMAIL_REFRESH_TOKEN` is a *refresh* token, and the Google OAuth app is appropriately configured. Testing-mode tokens commonly expire after seven days.
- **`Gmail access denied`**: Check Gmail API is enabled, `gmail.send` was authorized, the sender Gmail matches, and you're within Gmail sending limits.
- **`Verification email could not be sent`**: Open Railway → Deployments → current deployment → View Logs for the HTTP status (don't post secret values).
- **No new Railway deploy**: Check `git log -1 --oneline` locally, compare the commit displayed on GitHub and Railway; verify the repository and Root Directory.
- **SQLite data missing**: Do *not* delete the persistent `/data` volume. Check `QUEUEWISE_DB_PATH` points at `/data/queuewise.db`. Don't overwrite it with an empty local database.

## 6. Security & limitations

Gmail API email verification confirms **control of an email inbox**; it does not prove official CvSU student/alumni enrollment. Gmail's free personal-account sending limits and Google OAuth application policies still apply. Avoid using real student records in the academic prototype.

The 56 automated tests use **mock email delivery**, not the live Gmail API. A live test in Railway with your authorized sender is required to confirm actual delivery.
