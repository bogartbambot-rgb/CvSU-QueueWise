# CvSU QueueWise — Functional and Error-Handling Test Guide

Run locally via `python run.py` and visit **http://127.0.0.1:8000**. The steps below are for an *empty database* unless otherwise stated. Staff credentials are in `README.md`.

| # | Test scenario | Steps | Expected behavior |
|---|---|---|---|
| 01 | Valid request | Document Request → enter `Juan Dela Cruz`, Certificate of Grades, Graduating, a future date → Submit | Green success popup, automatically assigned `REQ-0001` (if first-ever), request saved in SQLite |
| 02 | Missing name | Leave Full name empty → Submit | Browser prevents submission |
| 03 | Incomplete name | Enter `Juan` → Submit | Server rejects complete-name validation, no new request |
| 04 | Numeric name | Enter `Juan 123` → Submit | Clean validation error, no new record |
| 05 | Missing document type | Leave document type unselected → Submit | Browser/server stops submission |
| 06 | Past deadline | Select yesterday (via manually crafted API if browser prevents selection) | Server returns a validation error, no record inserted |
| 07 | Invalid category | Submit unknown category through API | Server rejects it |
| 08 | Auto-generated unique ID | Submit two valid requests | Different `REQ-XXXX` IDs, monotonic IDs even after restart |
| 09 | Public tracking | Enter the generated ID on Dashboard → Check status | Minimal Pending/Processing/Processed details and event history shown; requester name is not revealed |
| 10 | Unknown ID | Track `REQ-9999` (when not in DB) | “No request was found” error; no crash |
| 11 | Admin restrictions | As Guest try `/api/admin/requests` | HTTP 401; no priority list or private names disclosed |
| 12 | Bad credentials | Sign in with incorrect admin password | Clear incorrect-login error; no admin access |
| 13 | Staff login | Top-right **Sign in** / sidebar **Registrar sign in** → dedicated login page | Staff dashboard, private request table, processing tools become available |
| 14 | Priority ranking | Load sample data → Document Request → Priority ranking | Higher scores first; ties broken by deadline, arrival, ID |
| 15 | FIFO history | Go to FIFO arrivals | Request IDs stay in chronological order even after processing |
| 16 | Process highest priority | As staff click **Process next** | Highest Pending request becomes Processed; record stays searchable |
| 17 | Empty queue | Process all pending records → click Process next | Action is disabled in UI or API returns “pending queue is empty,” not a server crash |
| 18 | Illegal status transition | Try Pending → Ready for Release via API | HTTP 409, previous status unchanged |
| 19 | Valid status transitions | Pending → Processing → Ready for Release → Processed | Status and event timeline update at each transition |
| 20 | Notifications | Submit requests / change status → Notifications | New in-app activity appears; staff can mark all as read |
| 21 | Light/dark mode | Click moon/sun icon and refresh | Theme changes and is restored from browser preferences |
| 22 | Help popup | Click `?` in top-right | Modal titled **How the system works**; tabs explain Student / Alumni and Registrar Staff flows |
| 23 | Responsive sidebar | Resize to mobile width | Sidebar is hidden behind hamburger; panel opens/closes with overlay |
| 24 | SQLite restart | Submit a request, stop server, restart, track the same ID | Record persists |
| 25 | 150-record capacity | Staff → Load sample data repeatedly (or run automated test) | Heap invariant preserved, hash table grows, records remain searchable |
| 26 | Update admin password | Profile → Security settings → enter current + strong new password | Password updated; logged out; old credentials stop working |
| 27 | CSRF | Call POST API without `X-CSRF-Token` | HTTP 403; mutation does not happen |
| 28 | Offline support | Visit once online; then disconnect and reload | Offline explanation page appears; live submission/tracking needs a server connection |

| 29 | Visible logout | Sign in → click **Log out** in the top-right or sidebar | Session ends, returns to login screen, private API access is blocked |
| 30 | Dedicated login page | Click Sign in or visit `/#login` | Two-column green login page; name and password fields, public portal buttons |
| 31 | Install PWA button | Click **Install app** | Native install prompt when supported, otherwise clear manual Chrome/Edge instructions |
| 32 | New PWA files | Open `/manifest.webmanifest`, `/sw.js`, and `/static/css/auth.css` | Valid manifest, updated service-worker cache version, CSS available |
| 33 | Existing PWA upgrade | Upgrade app files; close installed window; browser hard-refresh | New interface loads rather than old cached app JS or CSS |

## Recommended automated tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

There are **20 passing tests** as of packaging. The tests create temporary SQLite databases; they do not modify your working `instance/queuewise.db`.

## Data-structure versus full HTTP cost

For the course demonstration, **individual ADT operations** have their standard complexity:

| Operation | ADT operation cost | Implementation considerations |
|---|---|---|
| FIFO enqueue | O(1) | Singly linked queue with tail pointer |
| Heap insert/extract-min | O(log n) | Binary heap; n = Pending entries |
| Bottom-up heapify | O(n) | Current pending scores are refreshed first |
| Hash get / contains | O(1) average, O(N) worst | Separate chaining, resizing to lower collision rate |
| Priority sorted copy | O(n log n) | Does not alter original heap |
| Process next with score refresh | O(n) | O(n) refresh dominates heap extract O(log n) |

**Important nuance:** In this SQLite-backed web implementation, ADTs are **reconstructed from current persisted rows for each database operation** for easy consistency and restart recovery. This adds **O(N) snapshot hydration** to the total HTTP operation (including public hash lookup). Never claim O(1) end-to-end API time just because the internal hash-table `get` is O(1) average. This trade-off simplifies the prototype and remains practical at 100–150 records. A production system can maintain a persistent in-memory index and version-aware synchronization to reduce hydration cost.
