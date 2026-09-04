# LAMS - Lab Activity Monitoring System

One website on the internet that shows, live, which lab computers are switched
on and whether a particular program is open on them. Any lab, any university,
any browser, anywhere.

| File | What it is |
|---|---|
| `agent.py` | Runs on each lab computer. Reports its status every 5 seconds. Built into `agent.exe`. |
| `dashboard.py` | The website. Runs once, hosted online. Serves every lab. |
| `index.html` | The page itself - cards, icons, and the lab dropdown. |
| `render.yaml` | Tells Render.com how to run the dashboard. You never type a build command. |
| `config_template.json` | Example settings file (the agent writes its own, so you rarely need this). |

There is **no database**. The dashboard keeps computers in a plain Python
dictionary in memory. The agents re-report every 5 seconds, so if the server
restarts it refills itself within seconds.

---

## How it fits together

```
   Comilla PC-01  \
   Comilla PC-03   \
   Dhaka   PC-01    ---->  ONE dashboard hosted on Render  ---->  your browser
   (any new lab)   /       https://your-app.onrender.com          (anywhere)
```

Every agent sends its `lab_id` with each report. The dashboard stores it as a
label and the page has a dropdown to show one lab at a time. A lab that has
never been seen before simply appears in the dropdown the first time one of its
computers reports - nothing to configure on the server.

---

## Part 1 - Put the dashboard online (once, ~10 minutes)

**1. Put this folder on GitHub.**

```
git init
git add .
git commit -m "LAMS"
```

Then create an empty repository on github.com and follow the two `git remote` /
`git push` lines it shows you.

**2. Deploy on Render.**

1. Sign up free at <https://render.com> with your GitHub account
2. **New +** -> **Blueprint** (Render reads `render.yaml` and fills everything in)
3. Pick your repository -> **Apply**
4. Wait for the build (2-3 min). You get an address like
   `https://lams-dashboard.onrender.com`

**Open that address in a browser.** You should see the empty dashboard. That
address is now your whole project's home - keep it, you will paste it once more
below.

> **Free tier note:** if nobody talks to it for 15 minutes, Render puts it to
> sleep, and the next request takes ~30-50 seconds to wake it. While agents are
> running they ping it every 5 seconds, so it stays awake. On demo day, open the
> page a minute before you present.

**3. Bake your address into the agent.**

Open [agent.py](agent.py), find this line near the top, and paste your Render
address in:

```python
DASHBOARD_URL = "https://lams-dashboard.onrender.com"
```

That is the one edit that makes installing on lab computers a double-click.

## Part 2 - Build the `.exe` (once)

```
pip install -r requirements.txt
pip install pyinstaller
python -m PyInstaller --onefile agent.py
```

The result is `dist\agent.exe`. That single file is what you install everywhere.

## Part 3 - Install on a lab computer (~20 seconds each)

1. Copy `agent.exe` onto the computer, anywhere
2. Double-click it
3. It asks four questions. **Press Enter for all of them except the lab id and
   the computer name:**

```
First-time setup for this computer.
Press Enter to accept the [suggestion] in brackets.

Dashboard address [https://lams-dashboard.onrender.com]:
Lab id           [comilla-cse-lab]:
Computer name    [DESKTOP-6QS9FVO]: PC-01
Program to watch [chrome.exe]:
```

It saves the answers to `config.json` next to itself and **starts monitoring
immediately** - no restart, no Notepad. The computer appears on the website
within about 5 seconds.

To change anything later, edit that `config.json` by hand, or delete it and run
the `.exe` again to be asked afresh.

---

## Trying it on your own laptop first

**Terminal 1 - the dashboard:**

```
pip install -r requirements.txt
python dashboard.py
```

Open <http://127.0.0.1:8000>.

**Terminals 2, 3, 4 - three "computers" in two different labs:**

```
python agent.py demo/pc-01-comilla/config.json
python agent.py demo/pc-03-comilla/config.json
python agent.py demo/pc-02-dhaka/config.json
```

All three appear. Use the **Lab** dropdown to switch between *All labs*,
*comilla-cse-lab* (2 computers) and *dhaka-lab* (1 computer).

Notice that Comilla and Dhaka **both have a computer called PC-01**, and they do
not overwrite each other. That is deliberate: the dashboard stores computers
under the pair *(lab id + computer name)*, not the name alone.

*(These demo configs point at `127.0.0.1` for local testing, and pass the
settings file as an argument so three "computers" can run from one folder. A
real `agent.exe` never needs that - it just reads the `config.json` beside it.)*

---

## The status words

Worked out by the dashboard, in this exact order:

| Status | Meaning |
|---|---|
| Offline (black) | Nothing heard from this computer for over 30 seconds. |
| In Use (green) | The program in `watch_process` is running on it. |
| Online (blue) | It is reporting, but that program is not running. |

**Online means "switched on and reporting", In Use means "the program we care
about is actually open".** A computer can be Online with somebody browsing the
web on it - the *Using:* line on the card tells you that, not the status word.
Keeping those two ideas separate is what keeps the logic to three lines.

Online/Offline is decided **at the moment the page asks for data**, by comparing
each computer's last report time to the current time. No background task, no
timer anywhere in the project.

---

## Privacy and consent

Monitoring is disclosed, never hidden. Every time the agent starts - **before it
reads anything** - it prints a notice on that computer's screen saying
monitoring is active and exactly what is collected.

Recorded: whether the watched program is running, the **name** of the
application in front (e.g. "Chrome"), and the time of the last report.

**Not** recorded: screen contents, keystrokes, window titles, page addresses,
file names, or anything typed. The dashboard cannot show what a student is doing
inside an application - only which application is in front.

---

## Design decisions (and the honest reasons)

* **No database.** Agents re-report every 5 seconds, so a restarted server
  rebuilds itself in seconds. Also, Render's free tier wipes the filesystem on
  every restart, so a SQLite file would give false comfort, not real
  persistence. If the project needed *history* - "how often was PC-01 in use
  last month" - that is exactly when a real database earns its place.
* **One shared dashboard, not one per lab.** Chosen so the whole system is one
  address you can open from anywhere, and installing a lab computer needs no
  server work at all. The trade-off is written up honestly below.
* **No login.** Anyone with the address can view it. See the Q&A.
* **No background task for the offline check** - see above.
* **No WebSockets.** The page asks for fresh data every 3 seconds with `fetch()`.
  Simple, and plenty fast for a lab.

---

## How the whole thing works (to read out during the demo)

> On every lab computer there is a small program called the agent. Every five
> seconds it checks two things Windows gives us for free: whether a particular
> program - say Chrome - is running, and which application is currently in front
> on the screen. It packs that into a short message together with the computer's
> name and its lab id, and sends it over the internet to our dashboard, which is
> hosted on Render. The dashboard keeps the newest message from each computer in
> a dictionary in memory, filed under the lab it came from - no database,
> because every computer reports again a few seconds later anyway. The web page
> asks the server for that data every three seconds and draws one card per
> computer, and a dropdown lets you look at one lab at a time. The server decides
> the status word at the moment the page asks: if it has not heard from a
> computer for thirty seconds it is Offline, otherwise if the watched program is
> running it is In Use, otherwise it is just Online. Because it is one shared
> dashboard on the internet, adding a whole new lab needs no work on the server
> at all - the first computer that reports with a new lab id makes that lab
> appear in the dropdown by itself.

---

## Likely questions from the teacher, with short answers

**What stops one lab's computers mixing with another's?**
Every report carries a `lab_id`, and the dashboard files each computer under the
pair *(lab id, computer name)*. The page shows one lab at a time through the
dropdown, so labs never visually mix - and two labs can both have a "PC-01"
without clashing. I can show that live: my demo has exactly that.

**But is that enforced, or just a label?**
Honestly, it is a label. This version accepts a report from any lab id by
design, because that is what lets a new lab join with zero server configuration.
If I needed it enforced, I would keep a list of allowed lab ids on the server and
reject anything else with HTTP 403 - about three lines. I chose ease of joining
over hard isolation, and I know which one I gave up.

**Anyone with the link can see it. Isn't that a security problem?**
Yes, that is the real limitation. There is no login in this version. For a class
project on a private lab network it is acceptable; the next step would be a
password on the dashboard page, or restricting it to the university's network.
I would not deploy it publicly at a real university without that.

**What if the server restarts? You lose everything.**
Nothing that matters. Every computer reports again within five seconds, so the
dashboard rebuilds itself almost immediately. What it shows is a live snapshot,
not a history.

**Why no database, then?**
Because I only show the *current* state, and that state refreshes itself every
few seconds. A database would add a whole component with nothing to gain. On top
of that, Render's free tier resets the filesystem when the service restarts, so
a SQLite file would not even survive - it would look like persistence without
being persistence.

**Is this spying on students?**
No, and it is built so it cannot be. It records only whether one named program
is running and the *name* of the application in front - never screen contents,
keystrokes, window titles or anything typed. The agent prints a notice on the
screen every time it starts, before it reads anything, so monitoring is always
disclosed and never hidden.

**Why is it "Online" when somebody is clearly using the computer?**
Two different questions, kept separate on purpose. Online means the computer is
switched on and reporting. In Use means the specific program I am watching is
open. If a student is browsing the web, the card says Online and the
*Using: Chrome* line tells you what they are on.

**How does a new lab get added?**
It just reports. The first computer that sends a new lab id makes that lab appear
in the dropdown. No server change, no redeploy, no database migration.

**Why a config file instead of building a different `.exe` per lab?**
So the `.exe` is one single file everywhere. Installing on a computer is
double-click, answer two questions. That is also how real software does it.

**What if the internet or the server is down when an agent starts?**
The agent prints "dashboard unreachable, retrying" and keeps looping. It never
crashes. I can demonstrate that by starting an agent before the dashboard.

**How does the page update itself?**
Plain JavaScript: `fetch("/data")` inside a `setInterval` every three seconds,
then it redraws the cards. No WebSockets, no framework, no build step.

**Why four endpoints?**
`GET /` sends the page, `GET /data` sends the numbers the page draws,
`GET /labs` fills the dropdown, and `POST /report` is where agents send status.
The page and its data are separate requests - that is what lets it refresh
without reloading.

**Could a student just close the agent?**
Yes, in this version - and then their computer goes Offline within thirty
seconds, which is itself visible on the dashboard. Making it tamper-proof would
mean running it as a Windows service with restricted user rights, which is the
natural next step but beyond a class project.

**How do you know which application is in front without an extra library?**
Windows exposes it through its own API. `ctypes` is in Python's standard library
and can call `GetForegroundWindow`, then I ask `psutil` for that window's process
name. It is wrapped in try/except and falls back to "unknown", because a locked
screen has no foreground window and that must not stop the loop.

**Why does the `.exe` need that `sys.frozen` code?**
PyInstaller `--onefile` unpacks the code into a temporary folder when it runs, so
`__file__` points there, not at the folder holding the `.exe`. Without that check
the `.exe` would look for `config.json` in the wrong place and appear to ignore
its settings completely.

**How would this scale to a hundred computers?**
Each computer sends one small message every five seconds, so a hundred computers
is twenty small requests a second - nothing for the server. The dictionary holds
a hundred small entries. What I would add first is history, and that is where a
real database comes in.
