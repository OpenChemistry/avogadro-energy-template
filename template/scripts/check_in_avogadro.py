#!/usr/bin/env python3
"""Check this plugin's energy models inside a real Avogadro, over JSON-RPC.

    python scripts/check_in_avogadro.py --app /path/to/Avogadro2.app

For each [[tool.avogadro.energy-models]] in pyproject.toml it starts a fresh
Avogadro (so the first energy call is a cold model start) and checks that the
model is offered, that the first and second energy are finite, that a short
optimization lowers the energy, that a periodic model handles a crystal, and
that charge-aware models handle an anion while the others are not offered.
Exit status 0 means every check passed.

The plugin must already be installed in that Avogadro (Manage Plugins >
Install from Directory...), because the app runs with your real settings.
Needs Python 3.11 or newer and nothing else. macOS and Linux only.

A first-call failure on a released Avogadro may only mean that its plugin
start-up budget (how long it waits for a model to load) is too short for a
model that takes a while to start; development builds wait up to 60 s.
"""

import argparse
import json
import math
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WARN_SECONDS = 30.0
BUDGET = 60.0


# --- a minimal client for Avogadro's length-prefixed JSON-RPC -------------
def socket_path(name):
    if sys.platform == "darwin":
        return os.path.join(tempfile.gettempdir(), name)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        return os.path.join(runtime, name)
    return os.path.join(tempfile.gettempdir(), "avogadro-%d" % os.getuid(), name)


class RPCError(Exception):
    pass


def read_exactly(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Avogadro closed the connection")
        data += chunk
    return data


def call(name, method, params=None, wait=False, timeout=60):
    """One request on a fresh connection. Returns the result (the command's
    data for a waited command)."""
    options = dict(params or {})
    if wait:
        options.update(wait=True, timeout=timeout)
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": options}
    ).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout + 10)
        sock.connect(socket_path(name))
        sock.sendall(struct.pack(">I", len(body)) + body)
        (size,) = struct.unpack(">I", read_exactly(sock, 4))
        reply = json.loads(read_exactly(sock, size))
    if "error" in reply:
        raise RPCError(reply["error"].get("message", "").strip())
    result = reply.get("result")
    if wait and isinstance(result, dict):
        return result.get("data", {})
    return result


# --- molecules ---------------------------------------------------------------
def cjson(numbers, coords, charge=0, cell=None, fractional=None):
    doc = {
        "chemicalJson": 1,
        "name": "check",
        "atoms": {
            "elements": {"number": numbers},
            "coords": {"3d": [c for xyz in coords for c in xyz]},
        },
        "properties": {"totalCharge": charge, "totalSpinMultiplicity": 1},
    }
    if cell:
        doc["unitCell"] = dict(a=cell, b=cell, c=cell, alpha=90.0, beta=90.0, gamma=90.0)
        doc["atoms"]["coords"]["3dFractional"] = [c for xyz in fractional for c in xyz]
    return json.dumps(doc)


WATER = cjson([8, 1, 1], [[0, 0, 0.117], [0, 0.757, -0.469], [0, -0.757, -0.469]])
DISTORTED = cjson([8, 1, 1], [[0, 0, 0.117], [0, 0.95, -0.55], [0.3, -0.65, -0.35]])
HYDROXIDE = cjson([8, 1], [[0, 0, 0], [0, 0, 0.97]], charge=-1)
_SITES = [[0, 0, 0], [.5, .5, 0], [.5, 0, .5], [0, .5, .5],
          [.25, .25, .25], [.75, .75, .25], [.75, .25, .75], [.25, .75, .75]]
# Diamond-cubic silicon, conventional cell (closed shell).
SILICON = cjson([14] * 8, [[x * 5.431 for x in s] for s in _SITES],
                cell=5.431, fractional=_SITES)


# --- the checks ----------------------------------------------------------------
def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def models_from_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as handle:
        data = tomllib.load(handle)
    return [
        (m["identifier"], m.get("support", {}))
        for m in data["tool"]["avogadro"]["energy-models"]
    ]


def timed(name, method, params, timeout=120):
    started = time.monotonic()
    try:
        data, error = call(name, method, params, wait=True, timeout=timeout), None
    except (RPCError, OSError, ValueError) as exc:
        data, error = {}, str(exc) or repr(exc)
    return time.monotonic() - started, data or {}, error


def offered(name):
    return (call(name, "listForceFields", wait=True, timeout=60) or {}).get("names", [])


def load(name, content):
    call(name, "loadMolecule", {"content": content, "format": "cjson"})


def start_app(app, name):
    log = open(Path(tempfile.gettempdir()) / (name + ".log"), "wb")
    process = subprocess.Popen(
        [app, "--rpc-name", name, "--skip-autosave"],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Avogadro exited with code %s" % process.returncode)
        try:
            call(name, "moleculeInfo", timeout=5)
            return process
        except (OSError, RPCError, ValueError):
            time.sleep(0.5)
    process.kill()
    raise RuntimeError("Avogadro did not answer RPC within 90 s")


def check(app, model, support):
    """Run the checks on one model; returns [(check, ok, detail)]."""
    out = []
    name = "avocheck-%d" % os.getpid()
    process = start_app(app, name)

    def add(what, ok, detail):
        out.append((what, ok, detail))
        print("  %-9s %-4s %s" % (what, "ok" if ok else "FAIL", detail), flush=True)
        return ok

    try:
        deadline = time.monotonic() + 60
        while True:  # plugins register just after RPC starts answering
            load(name, WATER)
            if model in offered(name) or time.monotonic() > deadline:
                break
            time.sleep(1)
        is_offered = model in offered(name)
        if not add("offered", is_offered,
                   "yes" if is_offered else
                   "not listed; is the plugin installed in this Avogadro?"):
            return out

        run = {"method": model}
        seconds, data, error = timed(name, "energy", run, timeout=int(BUDGET) * 2)
        energy = data.get("energy")
        if error or not finite(energy):
            hint = ""
            if "timed out" in (error or "") or seconds >= BUDGET - 5:
                hint = (" -- this Avogadro may predate the plugin start-up budget;"
                        " try a development build")
            add("first", False, "%s after %.1f s%s" % (error or energy, seconds, hint))
            return out
        add("first", seconds < BUDGET, "%.1f in %.1f s%s" % (
            energy, seconds, " (slow!)" if seconds > WARN_SECONDS else ""))

        seconds, data, error = timed(name, "energy", run)
        again = data.get("energy")
        add("second", not error and finite(again)
            and abs(again - energy) <= 1e-6 * max(1, abs(energy)),
            error or "%.1f in %.1f s" % (again, seconds))

        load(name, DISTORTED)
        _, data, _ = timed(name, "energy", run)
        before = data.get("energy")
        seconds, data, error = timed(name, "optimize", dict(run, steps=300), 300)
        after = data.get("energy")
        add("optimize", not error and finite(before) and finite(after) and after < before,
            error or "%.2f -> %.2f in %s steps (%.1f s)" % (
                before, after, data.get("steps"), seconds))

        load(name, SILICON)
        if support.get("unit-cell"):
            if add("crystal", model in offered(name), "offered for a crystal"):
                seconds, data, error = timed(name, "energy", run, 300)
                add("crystal", not error and finite(data.get("energy")),
                    error or "%.1f in %.1f s" % (data["energy"], seconds))
        else:
            add("crystal", model not in offered(name), "not periodic, not offered")

        load(name, HYDROXIDE)
        if support.get("ions"):
            if add("anion", model in offered(name), "offered for an anion"):
                seconds, data, error = timed(name, "energy", run, 300)
                add("anion", not error and finite(data.get("energy")),
                    error or "%.1f in %.1f s" % (data["energy"], seconds))
        else:
            _, _, error = timed(name, "energy", run, 60)
            add("anion", model not in offered(name) and error is not None,
                "not offered and an explicit request is refused")
    except Exception as exc:  # a dead app or a transport error
        add("app", False, repr(exc))
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--app", required=True, help="Avogadro2 binary or .app")
    parser.add_argument("--model", action="append", help="only this identifier")
    args = parser.parse_args()

    app = Path(args.app).expanduser()
    if app.suffix == ".app":
        app = app / "Contents" / "MacOS" / "Avogadro2"
    if not app.is_file():
        parser.error("no such executable: %s" % app)

    failed = False
    for model, support in models_from_pyproject():
        if args.model and model not in args.model:
            continue
        print(model, flush=True)
        try:
            results = check(str(app), model, support)
        except RuntimeError as exc:
            print("  app       FAIL %s" % exc)
            results = []
        failed |= not results or not all(ok for _, ok, _ in results)
    print("FAILED" if failed else "all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
