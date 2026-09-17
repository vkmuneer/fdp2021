# Brainwave Academy - Management System

A mobile-friendly web application to manage Brainwave Academy (Mukkam Road, Omassery) -
classes 9, SSLC, +1 and +2 Science, with divisions. Built with Flask so it runs from any
phone, tablet or computer through a normal web browser (no app-store install needed - you
can even "Add to Home Screen" on a phone for an app-like icon).

## Features

- **Admin login** and **Teacher login** with role-based access.
- **Student management** - admission details, class & division, parent name/WhatsApp
  number, address, discount/scholarship (recorded per student with a reason).
- **Teacher management** - create teacher logins and assign each teacher to one or more
  class divisions.
- **Class & division management** - add divisions per class and edit each class's base
  course fee. Default fees are pre-loaded: Class 9 = ₹10,000, SSLC = ₹12,500,
  +1 = ₹20,000, +2 = ₹20,000.
- **Attendance marking** - teachers pick their division and date, then tick/untick each
  student (Present/Absent) with big touch-friendly switches, with "Mark All Present /
  Absent" shortcuts.
- **Automatic absence notification** - when attendance is saved, every absent student's
  parent is notified on WhatsApp automatically (if a Twilio WhatsApp sender is configured)
  or via a one-tap `wa.me` link for office staff to send manually - no paid API is
  required to get started.
- **Fee collection with installments** - record partial payments against a student's
  total fee (class fee minus discount); pending balance is always shown and payments
  cannot exceed it.
- **Accounts reports** - daily finance report (collections by date/mode/class), pending
  fees report, discount/scholarship report, and a daily attendance report.
- **Brainwave Academy branding** - the app uses the academy's teal-to-blue gradient
  colour theme throughout (`app/static/img/logo.svg`, `app/static/css/style.css`).
  Replace `logo.svg` with the exact official logo file at any time; the color variables
  in `style.css` (`--bw-teal`, `--bw-blue`, `--bw-dark-teal`) can be tuned to match it
  exactly.

## Getting started

```bash
cd brainwave_academy
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env: set a real SECRET_KEY and admin password
python run.py
```

Open `http://localhost:5000` in a browser (or `http://<your-computer-ip>:5000` from a
phone on the same Wi-Fi). The database (SQLite file `brainwave.db`) and a default admin
account (`admin` / `admin123`, or whatever you set in `.env`) plus the four classes are
created automatically the first time the app runs. **Log in and change the admin
password immediately** (top-right menu -> your name -> Change Password).

### Setting up teachers and students

1. Log in as admin -> **Classes** -> add divisions (e.g. A, B) for each class you need.
2. **Teachers** -> Add Teacher -> set a username/password and tick the class divisions
   they teach.
3. **Students** -> Add Student -> pick the class/division; the fee defaults from the
   class but can be overridden per student, and any discount/scholarship is entered here
   with a reason.
4. Teachers log in with their own username/password and only see their assigned
   divisions, under **Attendance** and **My Students**.

### Enabling automatic WhatsApp sending (optional)

By default, absence messages generate a one-tap WhatsApp link for the office to send.
To send them fully automatically instead, sign up for Twilio's WhatsApp sandbox/API and
set these in `.env`:

```
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

No code changes are needed - the app detects these and switches to automatic sending.

### Deploying so it's reachable from anywhere

The repo already includes a `Procfile` (`web: gunicorn run:app`) and a `render.yaml`
blueprint at the repo root, so it deploys to [Render](https://render.com) with almost no
manual setup:

1. Push this repo to your own GitHub account (or use it directly if it's already there).
2. On Render: **New +** -> **Blueprint** -> connect the repo -> pick the branch that has
   this code -> Render detects `render.yaml` and shows one service, `brainwave-academy`.
3. Click **Apply**. When prompted, set `DEFAULT_ADMIN_PASSWORD` (required) and leave
   `DATABASE_URL`, `TWILIO_*` blank unless you have them.
4. After the build finishes, Render gives you a public URL like
   `https://brainwave-academy-xxxx.onrender.com` - that's the link to share/bookmark.

**Important - data persistence:** the default setup uses a local SQLite file. On
Render's free plan the filesystem is not guaranteed to survive every restart/redeploy,
which is fine for trying it out but risky for real fee/attendance records. For real use,
either:
- attach a Render **persistent disk** to the service and point `DATABASE_URL` at a file
  on it (small paid add-on), or
- create a Render **PostgreSQL** database and set the service's `DATABASE_URL` to its
  connection string - the app already supports Postgres (`psycopg2-binary` is in
  `requirements.txt` and `postgres://` URLs are normalized automatically), no code
  changes needed.

Alternatives that also work well for a small tuition centre: **PythonAnywhere**'s free
tier (persistent disk, manual setup via their dashboard - no blueprint automation) or
any VPS behind Nginx + Let's Encrypt for HTTPS. Once deployed, any phone with a browser
can use it - no native app installation is required.

## Project structure

```
brainwave_academy/
  app/
    __init__.py        # app factory, seeds default classes/admin on first run
    models.py           # SQLAlchemy models (Student, Teacher, FeePayment, Attendance, ...)
    extensions.py        # Flask-SQLAlchemy / Flask-Login setup
    auth/                # login/logout/change-password
    admin/                # student/teacher/class CRUD, fee collection, reports
    teacher/               # attendance marking + history, own students
    utils/whatsapp.py       # Twilio auto-send with wa.me manual-link fallback
    templates/                # Jinja2 templates (mobile-first Bootstrap 5 UI)
    static/                     # brand CSS, logo, PWA manifest
  config.py
  run.py
  requirements.txt
  .env.example
```

## Notes

- Fee logic: `total_fee = (per-student override, else class base fee) - discount`;
  `pending_fee = total_fee - sum(payments)`. Payment entry is blocked from exceeding the
  pending balance to avoid overpayment mistakes.
- Attendance is unique per student per day - re-saving updates the existing record and
  re-triggers WhatsApp notification logic only for whoever is unchecked/absent at
  save time.
- Deactivating a student or teacher hides them from active lists without deleting
  their history (payments/attendance are preserved).
