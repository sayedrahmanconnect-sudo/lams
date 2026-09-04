"""
LAMS Dashboard - one shared dashboard on the internet.

Every lab computer, from every lab, reports to this one server. Each report
carries a lab_id, which we use to LABEL the computer and to filter the page
by lab - not to reject anything.

Storage is a plain Python dictionary in memory. No database: the agents
re-report every 5 seconds, so if this server restarts it fills itself back
up within seconds on its own.

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

# ALL our storage: a plain dictionary in memory.
# The key is (lab_id, computer_name) - both together, so two different labs
# can each have a computer called "PC-01" without overwriting each other.
computers = {}


class Report(BaseModel):
    """
    The shape of the message an agent sends us.

    task_category is either "on-task" or "off-task: <keyword>" - the agent
    works this out for itself by checking the browser's window title against
    its own watch_sites list. That raw window title is never part of this
    message and never reaches this server.
    """
    lab_id: str
    computer_name: str
    watch_process: str
    watch_process_running: bool
    foreground_app: str
    task_category: str = "on-task"


@app.post("/report")
def report(report: Report):
    """An agent reports its status here. Every lab is welcome."""
    computers[(report.lab_id, report.computer_name)] = {
        "lab_id": report.lab_id,
        "computer_name": report.computer_name,
        "watch_process": report.watch_process,
        "watch_process_running": report.watch_process_running,
        "foreground_app": report.foreground_app,
        "task_category": report.task_category,
        "last_seen": datetime.now(),
    }
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

        result.append({
            "lab_id": computer["lab_id"],
            "computer_name": computer["computer_name"],
            "status": status,
            "watch_process": computer["watch_process"],
            "foreground_app": computer["foreground_app"],
            "task_category": computer["task_category"],
            "last_seen": computer["last_seen"].strftime("%H:%M:%S"),
            "seconds_ago": int(seconds_ago),
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
