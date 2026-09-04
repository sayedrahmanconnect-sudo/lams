"""
LAMS Agent - runs on each lab computer.

What it does, once every few seconds:
  1. checks if the program named in config.json is running   (psutil)
  2. checks which application is in front on screen           (ctypes -> Windows)
  3. sends both, plus its name and lab id, to the dashboard   (requests)

Run it with:   python agent.py
Build an exe:  pyinstaller --onefile agent.py
"""

import ctypes
import json
import os
import socket
import sys
import time

import psutil
import requests

# How often we report to the dashboard.
REPORT_EVERY_SECONDS = 5

# The dashboard everyone reports to. After deploying to Render, paste your own
# address here, rebuild the .exe once, and setting up a lab computer becomes a
# double-click with nothing to type.
DASHBOARD_URL = "https://lams-dashboard-pvc4.onrender.com"
DEFAULT_LAB = "comilla-cse-lab"
DEFAULT_WATCH = "chrome.exe"


def program_folder():
    """
    The folder our settings file lives in.

    TRAP: PyInstaller --onefile unpacks the code into a temporary folder, so
    __file__ does NOT point at the folder holding the .exe. sys.frozen is True
    only in that built .exe, and sys.executable is then the .exe itself.
    Without this the .exe would silently look for config.json in the wrong place.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)              # running as .exe
    return os.path.dirname(os.path.abspath(__file__))       # running as .py


def stop(message):
    """
    Print a message and quit.

    TRAP: a double-clicked .exe closes its window the instant it ends, so the
    message would flash past unread. When frozen we wait for Enter first.
    When run from a terminal we don't, so it doesn't block scripts.
    """
    print()
    print(message)
    if getattr(sys, "frozen", False):
        input("Press Enter to close...")
    sys.exit(1)


def config_path():
    """
    Where the settings file is.

    Normally: config.json sitting next to the program - that is how the .exe
    works in a real lab. I can also pass a settings file as an argument, which
    is only for the demo, where I run several fake computers on one laptop:
        python agent.py demo/pc-01-comilla/config.json
    """
    if len(sys.argv) > 1:
        return os.path.abspath(sys.argv[1])
    return os.path.join(program_folder(), "config.json")


def ask(question, default):
    """Ask one question, offering a default if I just press Enter."""
    answer = input(question + " [" + default + "]: ").strip()
    return answer or default


def first_time_setup(path):
    """
    Runs the very first time on a computer, when there is no settings file.
    Asks four questions and writes config.json, so nobody has to open Notepad.
    """
    print("First-time setup for this computer.")
    print("Press Enter to accept the [suggestion] in brackets.")
    print()

    try:
        settings = {
            "dashboard_url": ask("Dashboard address", DASHBOARD_URL),
            "lab_id": ask("Lab id          ", DEFAULT_LAB),
            "computer_name": ask("Computer name   ", socket.gethostname()),
            "watch_process": ask("Program to watch", DEFAULT_WATCH),
        }
    except EOFError:
        # No keyboard available (started by a script) - just use the defaults.
        settings = {
            "dashboard_url": DASHBOARD_URL,
            "lab_id": DEFAULT_LAB,
            "computer_name": socket.gethostname(),
            "watch_process": DEFAULT_WATCH,
        }

    with open(path, "w") as f:
        json.dump(settings, f, indent=2)

    print()
    print("Saved. To change any of this later, edit this file:")
    print("    " + path)
    print()


def load_config():
    """Read the settings file, asking the setup questions if there isn't one."""
    path = config_path()

    if not os.path.exists(path):
        first_time_setup(path)

    with open(path) as f:
        config = json.load(f)

    # Make sure nothing important is missing before we start looping.
    for field in ["dashboard_url", "lab_id", "watch_process"]:
        if not config.get(field):
            stop("The setting '" + field + "' is empty in:\n    " + path)

    # computer_name is optional: default to this Windows computer's own name.
    # The config can override it so I can fake PC-01, PC-02, PC-03 from one laptop.
    if not config.get("computer_name"):
        config["computer_name"] = socket.gethostname()

    return config


def is_process_running(process_name):
    """True if a program with this name is running right now."""
    for process in psutil.process_iter(["name"]):
        try:
            name = process.info["name"]
        except Exception:
            continue  # the process ended while we were looking at it
        if name and name.lower() == process_name.lower():
            return True
    return False


def get_foreground_window():
    """
    The app name AND the window title of whatever is currently in front.

    The title is only ever used locally, for a moment, to pull out a site
    name (see get_site_name below) - it is never put in the report we send to
    the dashboard. Returns ("unknown", "") if we cannot tell (locked screen,
    or a moment when nothing is focused). Wrapped in try/except so a failure
    here can never stop the reporting loop.
    """
    try:
        window = ctypes.windll.user32.GetForegroundWindow()
        if not window:
            return "unknown", ""

        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if not pid.value:
            return "unknown", ""

        name = psutil.Process(pid.value).name()       # e.g. "chrome.exe"
        name = name.split(".")[0]                     # e.g. "chrome"

        length = ctypes.windll.user32.GetWindowTextLengthW(window)
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(window, buffer, length + 1)

        return name.capitalize(), buffer.value         # ("Chrome", "YouTube - Chrome")
    except Exception:
        return "unknown", ""


# Only these apps' window titles are ever looked at - anything else (Word,
# Explorer, a game, ...) is skipped, and its title is never read at all.
BROWSER_APPS = ["chrome", "msedge", "firefox"]

# Site names longer than this are cut short before sending - a safety limit
# so nothing resembling a full sentence, email address, or long page title
# can slip through (see get_site_name below).
MAX_SITE_NAME_LENGTH = 30


def get_site_name(app_name, window_title):
    """
    The SITE NAME only (e.g. "ChatGPT", "YouTube", "Gmail") - never the full
    window title, never a URL, never an email address or message count.

    Browser tab titles almost always end with " - SiteName" (that suffix is
    added by the site itself, e.g. a YouTube tab is "Rick Astley - YouTube").
    We take only that last piece. Returns "" when this is not a browser, or
    when the title does not look like a normal "something - SiteName" shape -
    in both cases we show nothing rather than risk showing something messy.
    """
    if app_name.lower() not in BROWSER_APPS:
        return ""

    if " - " not in window_title:
        return ""

    site = window_title.rsplit(" - ", 1)[-1].strip()

    # Names the browser itself adds to every one of its windows (a New Tab
    # page, an empty window, a private window) - not a real site name.
    browser_labels = ["google chrome", "chrome", "microsoft edge", "msedge",
                       "mozilla firefox", "firefox", "new tab"]

    # Safety checks - if any of these fail, show nothing rather than guess.
    if not site or len(site) > MAX_SITE_NAME_LENGTH:
        return ""
    if "@" in site:                 # looks like an email address slipped in
        return ""
    if site.lower() in browser_labels:
        return ""

    return site


def show_consent_notice(config):
    """
    Shown on screen before we read anything, every time the agent starts.
    Monitoring is always disclosed, never hidden.
    """
    print("=" * 60)
    print(" LAB ACTIVITY MONITORING IS ACTIVE ON THIS COMPUTER")
    print("=" * 60)
    print(" This computer reports to the lab dashboard:")
    print("   - whether " + config["watch_process"] + " is running")
    print("   - the NAME of the application currently in front")
    print("   - if a browser: the SITE NAME only (e.g. \"YouTube\", \"Gmail\"),")
    print("     taken from the browser tab title")
    print("   - the time of its last report")
    print()
    print(" It does NOT record full window titles, page addresses, email")
    print(" addresses, message counts, screen contents, keystrokes, or")
    print(" anything you type.")
    print("=" * 60)
    print()


def main():
    config = load_config()
    show_consent_notice(config)

    url = config["dashboard_url"].rstrip("/") + "/report"
    print("Computer name : " + config["computer_name"])
    print("Lab id        : " + config["lab_id"])
    print("Reporting to  : " + url)
    print("Press Ctrl+C to stop.")
    print()

    while True:
        app_name, window_title = get_foreground_window()

        # The full window title is used right here, locally, for a moment, to
        # pull out just the site name - then it falls out of scope. It is
        # never put into "report" below, so it can never be sent anywhere.
        site_name = get_site_name(app_name, window_title)

        report = {
            "lab_id": config["lab_id"],
            "computer_name": config["computer_name"],
            "watch_process": config["watch_process"],
            "watch_process_running": is_process_running(config["watch_process"]),
            "foreground_app": app_name,
            "site_name": site_name,
        }

        # What this computer looks like right now, printed so I can show it live.
        if report["watch_process_running"]:
            local_status = "In Use  (" + config["watch_process"] + " is running)"
        else:
            local_status = "Online  (" + config["watch_process"] + " is not running)"
        using_line = report["foreground_app"]
        if report["site_name"]:
            using_line += " (" + report["site_name"] + ")"
        print(time.strftime("%H:%M:%S") + "  " + local_status +
              "  |  using: " + using_line)

        # TRAP: the dashboard may not be started yet, or may be turned off in the
        # middle of the demo. That must never crash the agent - warn and keep going.
        try:
            answer = requests.post(url, json=report, timeout=20)
            if answer.status_code != 200:
                print("   -> dashboard answered with status " +
                      str(answer.status_code))
        except Exception:
            print("   -> dashboard unreachable, retrying")

        time.sleep(REPORT_EVERY_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAgent stopped.")
