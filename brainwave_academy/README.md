# Brainwave Academy - Management System

A mobile-friendly web application to manage Brainwave Academy (Mukkam Road, Omassery) -
classes 9, SSLC, +1 and +2 Science, with divisions. Built with Flask so it runs from any
phone, tablet or computer through a normal web browser (no app-store install needed - you
can even "Add to Home Screen" on a phone for an app-like icon).

## Features

- **Admin login** and **Teacher login** with role-based access.
- **Student management** - admission details, class & division, parent name/WhatsApp
  number, address, place and the school the student currently studies in (both picked
  from an admin-managed master list - see **Master Data** below), and discount/scholarship
  (recorded per student with a reason).
- **Bulk add students from Excel** - download a ready-made `.xlsx` template, fill it in
  (only admission no., name, class, division and parent WhatsApp number are mandatory -
  everything else is optional), and upload it back to create many students at once.
  Unknown divisions/places/schools are added to the master lists automatically; bad rows
  are skipped with a clear reason shown on screen, valid rows are still added.
- **Teacher management** - create teacher logins, assign each teacher to one or more
  class divisions, and record which subject(s) they teach (multi-select from the
  **Master Data** subject list).
- **Master Data** - a dedicated admin page (top menu) to manage the master lists used as
  dropdowns elsewhere: **Subjects** (for teachers), and **Place** / **School** (for
  students). Add an entry once and it becomes selectable everywhere; a subject in use by
  a teacher can't be deleted, keeping the picker consistent as the school's own vocabulary
  instead of free text.
- **Class & division management** - add divisions per class and edit each class's base
  course fee. Default fees are pre-loaded: Class 9 = ₹10,000, SSLC = ₹12,500,
  +1 = ₹20,000, +2 = ₹20,000.
- **Attendance marking** - teachers pick their division and date, then tick/untick each
  student (Present/Absent) with big touch-friendly switches, with "Mark All Present /
  Absent" shortcuts. Live attendance status and a full attendance report (with a
  present/absent/not-marked breakdown per division) are one tap away from the top menu
  and the admin dashboard.
- **Automatic absence notification** - when attendance is saved, every absent student's
  parent is notified on WhatsApp automatically (if a Twilio WhatsApp sender is configured)
  or via a one-tap `wa.me` link for office staff to send manually - no paid API is
  required to get started.
- **Fee collection with installments** - record partial payments against a student's
  total fee (class fee minus discount); pending balance is always shown and payments
  cannot exceed it.
- **Pending-fee WhatsApp reminders with a GPay/UPI pay link** - from the Pending Fees
  report, send a reminder to one parent or to everyone with a pending balance at once.
  The message includes a link to a Brainwave-branded page with a "Pay via GPay/UPI"
  button pre-filled with the administrator's UPI ID and the exact amount due (set the
  UPI ID once under **Settings**).
- **Accounts reports** - fee collection report with **daily, monthly and custom
  date-range** views (by payment mode and by class), a **pending fees** report, a
  **class-wise** summary (expected/collected/pending + today's attendance per class), a
  **student-wise** ledger report, a discount/scholarship report, and an attendance report.
  Every report has a **Download PDF** button and a **Print** button (browser print/"Save
  as PDF" with a clean, navbar-free layout); a student's fee statement can also be
  downloaded as a PDF from their profile page.
- **Examinations** - create an exam for a class, add its subjects with their own max/pass
  marks (from the Master Data subject list), then enter marks per division/subject
  (teachers only see/enter their own assigned subjects and divisions; admin sees
  everything). Each exam gets an automatic **performance analysis**: pass/fail counts,
  subject-wise average/highest/lowest/pass-rate, and a full student ranking with
  percentage and grade - complete with bar/pie charts. Downloadable as a **PDF analysis
  report**, a **PDF report card per student**, or an **Excel export** of the full marks
  grid.
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
2. **Master Data** -> add the subjects your teachers handle, and the places/schools your
   students commonly come from - these populate the dropdowns in steps 3-4 below.
3. **Teachers** -> Add Teacher -> set a username/password, tick the class divisions and
   subjects they handle.
4. **Students** -> Add Student -> pick the class/division; the fee defaults from the
   class but can be overridden per student, place/school are picked from Master Data,
   and any discount/scholarship is entered here with a reason. For adding many students
   at once, use **Students -> Bulk Upload** instead: download the Excel template, fill in
   a row per student, and upload it back (new places/schools mentioned in the sheet are
   added to Master Data automatically).
5. Teachers log in with their own username/password and only see their assigned
   divisions, under **Attendance** and **My Students**.
6. **Settings** -> enter the administrator's UPI ID (e.g. `yourname@okaxis`) and payee
   name to enable the "Pay via GPay/UPI" link in fee reminder messages.
7. **Examinations** -> Create Exam -> pick the class and add its subjects with max/pass
   marks. Teachers then enter marks for their own subject/division under their own
   **Examinations** menu (or admin can enter any marks); either side can then open
   **View Report** for the pass/fail analysis, charts, and PDF/Excel downloads.

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
any VPS behind Nginx + Let's Encrypt for HTTPS (see below). Once deployed, any phone with
a browser can use it - no native app installation is required.

### Self-hosting on your own server/VPS (instead of Render)

This gives you full control - your data lives on a disk you own, with no third-party
platform in between. It needs a Linux **VPS** (a small cloud server with root/SSH
access) - a few INR/USD per month from any provider (DigitalOcean, Hostinger VPS, AWS
Lightsail, Linode, or a spare Linux machine at your office). Plain "shared hosting"
(the cheap cPanel plans meant for WordPress) usually can't run a Python app like this -
you need a VPS.

**1. One-time server setup** (SSH into your VPS as root or a sudo user):

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git nginx

# Create a dedicated user to run the app (safer than running as root)
sudo adduser brainwave
sudo su - brainwave

git clone https://github.com/vkmuneer/fdp2021.git
cd fdp2021/brainwave_academy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # set SECRET_KEY and DEFAULT_ADMIN_PASSWORD to real values, then save (Ctrl+O, Enter, Ctrl+X)
python run.py   # quick manual test - Ctrl+C to stop once it starts without errors
```

**2. Run it permanently as a background service** (so it survives reboots/crashes) -
exit back to your sudo user and use the systemd unit already included in the repo:

```bash
exit   # back to your sudo user
sudo cp /home/brainwave/fdp2021/brainwave_academy/deploy/brainwave.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brainwave
sudo systemctl status brainwave   # should show "active (running)"
```

**3. Put Nginx in front** (so it's reachable on the normal web port 80/443, and to add
free HTTPS) using the template also included in the repo:

```bash
sudo cp /home/brainwave/fdp2021/brainwave_academy/deploy/nginx.conf.example /etc/nginx/sites-available/brainwave
sudo nano /etc/nginx/sites-available/brainwave   # set server_name to your domain or server IP
sudo ln -s /etc/nginx/sites-available/brainwave /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Optional but strongly recommended if you have a domain name - free HTTPS:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Your app is now live at `http://your-server-ip` (or `https://yourdomain.com` after
certbot). No domain? Teachers can still use `http://your-server-ip` - it just won't show
a padlock, which matters less if it's only ever used inside your own network.

**Where your data is stored:** the SQLite file at
`/home/brainwave/fdp2021/brainwave_academy/brainwave.db` on that server's own disk -
entirely under your control, and it survives restarts/reboots (unlike Render's free
tier). Since it's now your responsibility (not a managed platform's), back it up: the
included `deploy/backup.sh` script copies it daily and keeps 30 days - wire it up with
`crontab -e` as the comments in that file explain.

**How to make changes whenever needed** - two options:

- *Quick config-only changes* (fees, classes, UPI ID, master data) don't need any code
  change at all - they're all editable from the Settings/Classes/Master Data pages in
  the app itself while it's running.
- *Actual code changes* (new features, wording, colors) follow this loop:
  1. Edit the code on **your own computer** (see the next section for what to install).
  2. Test it locally (`python run.py`, open `http://localhost:5000`).
  3. Commit and push to your GitHub repo (`git add -A && git commit -m "..." && git push`).
  4. On the server: `cd ~/fdp2021/brainwave_academy && git pull && sudo systemctl restart brainwave`.
     (If you changed `requirements.txt`, run `.venv/bin/pip install -r requirements.txt` first.)

### Setting up your own computer to edit the code

To open, edit and test this project locally you need:

- **Python 3.11+** - the language the app is written in.
- **Git** - to download (`clone`) the code and push your changes back to GitHub.
- **A code editor** - [Visual Studio Code](https://code.visualstudio.com/) (free) is the
  most common choice; install its Python extension for syntax highlighting and
  autocomplete. Any editor works, though (even Notepad++), since this is plain
  Python/HTML.

Then, to get a working local copy:

```bash
git clone https://github.com/vkmuneer/fdp2021.git
cd fdp2021/brainwave_academy
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open `http://localhost:5000` to see it running locally. From here you can open the
`brainwave_academy` folder in VS Code, make changes, and re-run `python run.py` to see
them - the same steps as **How to make changes whenever needed** above, minus the
server part.

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
