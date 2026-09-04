"""
LAMS Dashboard - one shared dashboard on the internet.

Every lab computer, from every lab, reports to this one server. Each report
carries a lab_id, which we use to LABEL the computer and to filter the page
by lab - not to reject anything.

Storage is plain Python dictionaries in memory - no database. The agents
re-report every 5 seconds, so the live view fills itself back up within
seconds of a restart. The activity history (the last 25 things each
computer used, with times) is kept the same way, and IS lost if this
server restarts - keeping it permanently would need a real database.

Four endpoints:
    POST /report   an agent sends its status here
    GET  /         the web page
    GET  /data     the computers as JSON (optionally one lab), polled by the page
    GET  /labs     the list of labs seen so far, for the dropdown

Run it locally:   python dashboard.py
On Render it is started by the command in render.yaml.
"""

import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

# A computer we have not heard from for this long is counted as Offline.
OFFLINE_AFTER_SECONDS = 30

app = FastAPI()

# ALL our storage: two plain dictionaries in memory.
# The key in both is (lab_id, computer_name) - both together, so two different
# labs can each have a computer called "PC-01" without overwriting each other.
computers = {}      # the latest report from each computer
history = {}        # what each computer has used, oldest first

# How many past entries to keep per computer. Old ones drop off the front, so
# memory can never grow without limit no matter how long this runs.
MAX_HISTORY = 25


class Report(BaseModel):
    """
    The shape of the message an agent sends us.

    site_name is the SITE NAME only (e.g. "YouTube", "ChatGPT", "Gmail") when
    the foreground app is a browser, or "" otherwise. The agent works this out
    for itself from the browser's window title; that full window title is
    never part of this message and never reaches this server - only the short
    site name, if one could be safely extracted.
    """
    lab_id: str
    computer_name: str
    watch_process: str
    watch_process_running: bool
    foreground_app: str
    site_name: str = ""


@app.post("/report")
def report(report: Report):
    """An agent reports its status here. Every lab is welcome."""
    now = datetime.now()
    key = (report.lab_id, report.computer_name)

    computers[key] = {
        "lab_id": report.lab_id,
        "computer_name": report.computer_name,
        "watch_process": report.watch_process,
        "watch_process_running": report.watch_process_running,
        "foreground_app": report.foreground_app,
        "site_name": report.site_name,
        "last_seen": now,
    }

    # Keep a history of what this computer has used. Agents report every 5
    # seconds, so we do NOT add an entry every time - we only start a new one
    # when what they are using actually changes. While it stays the same we
    # just push that entry's end time forward, which is what gives us "how
    # long they were on it".
    what = report.foreground_app
    if report.site_name:
        what += " - " + report.site_name

    entries = history.setdefault(key, [])
    if entries and entries[-1]["what"] == what:
        entries[-1]["until"] = now
    else:
        entries.append({"what": what, "since": now, "until": now})
        if len(entries) > MAX_HISTORY:
            entries.pop(0)              # drop the oldest

    return {"ok": True}


@app.get("/")
def home():
    """The dashboard web page."""
    folder = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(folder, "index.html"))


@app.get("/labs")
def labs():
    """The labs we have seen, for the dropdown on the page."""
    return {"labs": sorted(set(lab_id for lab_id, name in computers))}


@app.get("/data")
def data(lab_id: str = ""):
    """
    The current computers, as JSON. The page asks for this every few seconds.

    If lab_id is given (/data?lab_id=dhaka-lab) only that lab is returned -
    that is what the dropdown uses. If not, every lab is returned together.

    Online / Offline is worked out HERE, at the moment the page asks, by
    comparing each computer's last report time to now. No background task.
    """
    now = datetime.now()
    result = []

    for computer in computers.values():
        if lab_id and computer["lab_id"] != lab_id:
            continue

        seconds_ago = (now - computer["last_seen"]).total_seconds()

        # The status word, in this exact order.
        if seconds_ago > OFFLINE_AFTER_SECONDS:
            status = "Offline"                      # not heard from in a while
        elif computer["watch_process_running"]:
            status = "In Use"                       # the watched program is open
        else:
            status = "Online"                       # reporting, program not open

        # What this computer has used, newest first, with how long each was
        # in front. Times are sent as full timestamps rather than "17:36:58",
        # so the page can show them in the timezone of whoever is looking -
        # this server's own clock is UTC, which would confuse everyone.
        key = (computer["lab_id"], computer["computer_name"])
        entries = []
        for entry in reversed(history.get(key, [])):
            entries.append({
                "what": entry["what"],
                "since": entry["since"].isoformat(),
                "seconds": int((entry["until"] - entry["since"]).total_seconds()),
            })

        result.append({
            "lab_id": computer["lab_id"],
            "computer_name": computer["computer_name"],
            "status": status,
            "watch_process": computer["watch_process"],
            "watch_process_running": computer["watch_process_running"],
            "foreground_app": computer["foreground_app"],
            "site_name": computer.get("site_name", ""),
            "last_seen": computer["last_seen"].isoformat(),
            "seconds_ago": int(seconds_ago),
            "history": entries,
        })

    result.sort(key=lambda c: (c["lab_id"], c["computer_name"]))
    return {"computers": result}


if __name__ == "__main__":
    import uvicorn

    # Render tells us which port to use through this environment variable.
    port = int(os.environ.get("PORT", 8000))
    print("Dashboard starting on http://127.0.0.1:" + str(port))
    # host 0.0.0.0 so other computers can reach us, not just this one.
    uvicorn.run(app, host="0.0.0.0", port=port)
