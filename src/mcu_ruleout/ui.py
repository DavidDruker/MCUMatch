"""Local web UI: `mcu-ruleout ui`.

Serves one page and a small JSON API from this machine only (127.0.0.1). It runs your compiler
on source text sent from the page, so two guards keep other web pages from using it:
  * every request must carry the random token printed at start-up (it is part of the page URL);
  * the Host header must be this server's own address, which blocks DNS-rebinding tricks.
Only Python's standard library is used.
"""
from __future__ import annotations

import json
import re
import secrets
import shlex
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import examples, report
from .memory import decide, measure_sources
from .targets import builtin_target_paths, load_target
from .toolchain import find_toolchain

MAX_BODY = 1_000_000
MAX_FILES = 16
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}")
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_DEFINE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_.+-]*)?")
COMPILED = (".c", ".cc", ".cpp", ".S", ".s")
HEADERS = (".h", ".hpp")
_RUN_LOCK = threading.Lock()  # one build/emulation at a time


class UiError(ValueError):
    """A problem with the request that the page should show to the user."""


def _asset(name: str) -> bytes:
    return resources.files("mcu_ruleout").joinpath("ui_assets", name).read_bytes()


def _target(body: dict):
    paths = builtin_target_paths()
    tid = body.get("target")
    if tid not in paths:
        raise UiError(f"unknown target {tid!r}")
    return load_target(paths[tid])


def _symbol(body: dict, key: str, required: bool = True) -> str | None:
    value = (body.get(key) or "").strip()
    if not value:
        if required:
            raise UiError(f"'{key}' is required: the name of a function in your code")
        return None
    if not _SYMBOL.fullmatch(value):
        raise UiError(f"'{key}' must be a plain function name")
    return value


def _defines(body: dict) -> list[str]:
    out = [d for d in re.split(r"[\s,]+", body.get("defines") or "") if d]
    for d in out:
        if not _DEFINE.fullmatch(d):
            raise UiError(f"bad define {d!r}: use NAME or NAME=value")
    return out


def _flags(body: dict) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(body.get("cflags") or "-O2"))
    except ValueError as e:
        raise UiError(f"cannot parse compiler flags: {e}") from e


def _write_sources(body: dict, folder: Path) -> list[Path]:
    files = body.get("files")
    if not isinstance(files, list) or not files:
        raise UiError("add at least one source file")
    if len(files) > MAX_FILES:
        raise UiError(f"at most {MAX_FILES} files")
    compiled, seen = [], set()
    for f in files:
        name, text = (f.get("name") or "").strip(), f.get("content")
        if not _NAME.fullmatch(name) or not name.endswith(COMPILED + HEADERS):
            raise UiError(f"bad file name {name!r}: letters, digits, '_', '-', '.' and one of "
                          f"{', '.join(COMPILED + HEADERS)}")
        if name.lower() in seen:
            raise UiError(f"duplicate file name {name!r}")
        seen.add(name.lower())
        if not isinstance(text, str):
            raise UiError(f"{name}: no content")
        path = folder / name
        path.write_text(text, encoding="utf-8", newline="\n")
        if name.endswith(COMPILED):
            compiled.append(path)
    if not compiled:
        raise UiError("no file to compile: add a .c, .cpp or .S file")
    return compiled


def api_targets() -> list[dict]:
    out = []
    for tid, path in builtin_target_paths().items():
        t = load_target(path)
        out.append({
            "id": tid, "name": t.name, "core": t.core, "fpu": t.fpu.value,
            "flash_bytes": t.flash_capacity, "ram_bytes": t.ram_capacity,
            "max_clock_hz": t.max_clock_hz.value, "clock_note": t.max_clock_hz.note,
            "flash": [{"name": r.name, "size": r.size, "where": r.where, "condition": r.condition} for r in t.flash],
            "ram": [{"name": r.name, "size": r.size, "where": r.where, "condition": r.condition} for r in t.ram],
            "sources": [f"{s['title']} ({s['revision']})" for s in t.sources.values()],
        })
    return out


def api_examples() -> list[dict]:
    return [{"name": ex.name, "title": ex.title, "sizes": ex.defines} for ex in examples.all_examples().values()]


def api_example(name: str = "fir_f32") -> dict:
    try:
        ex = examples.get(name)
    except KeyError as e:
        raise UiError(str(e.args[0])) from e
    value, unit = re.fullmatch(r"([0-9.]+)(s|ms|us|ns)", ex.deadline).groups()
    return {"files": [{"name": ex.file, "content": ex.source()}],
            "entry": ex.entry, "measure": ex.measure, "cflags": ex.cflags,
            "deadline": value, "deadline_unit": unit, "sizes": ex.defines}


def _deadline(body: dict) -> float | None:
    from .timing import parse_duration

    if not str(body.get("deadline") or "").strip():
        return None
    try:
        return parse_duration(f"{body['deadline']}{body.get('deadline_unit') or 'us'}")
    except ValueError as e:
        raise UiError(str(e)) from e


def api_memory(body: dict) -> dict:
    target, entry, flags, defines = _target(body), _symbol(body, "entry"), _flags(body), _defines(body)
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-ui-") as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        sources = _write_sources(body, src)
        tc = find_toolchain()
        with _RUN_LOCK:
            measurements = measure_sources(tc, target, sources, [entry], flags, Path(tmp) / "build", [src], defines)
        if not any(m.ok for m in measurements):
            raise UiError("build failed:\n" + measurements[0].error.replace(" | ", "\n"))
        res = decide(target, measurements)
    inputs = {"sources": [s.name for s in sources], "entries": [entry], "user_flags": list(flags),
              "target_flags": list(target.gcc_flags), "defines": defines,
              "description": f"{', '.join(s.name for s in sources)}  entry={entry}"}
    return report.memory_json(res, inputs, report.versions(tc.version()))


def api_timing(body: dict) -> dict:
    from . import timing as T

    target, entry, flags, defines = _target(body), _symbol(body, "entry"), _flags(body), _defines(body)
    measure = _symbol(body, "measure", required=False)
    deadline = _deadline(body)
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-ui-") as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        sources = _write_sources(body, src)
        tc = find_toolchain()
        with _RUN_LOCK:
            builds = T.measure_sources(tc, target, sources, entry, measure, flags, Path(tmp) / "build", [src], defines)
    if not any(b.ok for b in builds):
        raise UiError(builds[0].error.replace(" | ", "\n"))
    res = T.decide(target, builds, deadline)
    built = f"{', '.join(s.name for s in sources)}  flags={' '.join(target.gcc_flags + flags)}"
    return report.timing_json(res, built, (), report.versions(tc.version(), res.trace.unicorn_model))


def api_shortlist(body: dict) -> dict:
    """Every built-in target (or the ones listed in `targets`) against one kernel."""
    from . import shortlist as S

    paths = builtin_target_paths()
    wanted = body.get("targets") or list(paths)
    if not isinstance(wanted, list) or any(t not in paths for t in wanted):
        raise UiError("unknown target in 'targets'")
    entry, flags, defines = _symbol(body, "entry"), _flags(body), _defines(body)
    measure = _symbol(body, "measure", required=False)
    deadline = _deadline(body)
    with tempfile.TemporaryDirectory(prefix="mcu-ruleout-ui-") as tmp:
        src = Path(tmp) / "src"
        src.mkdir()
        sources = _write_sources(body, src)
        tc = find_toolchain()
        with _RUN_LOCK:
            sl = S.run(tc, [load_target(paths[t]) for t in wanted], sources, entry, measure, flags,
                       Path(tmp) / "build", [src], defines, deadline)
    if not sl.ruled_out and not sl.remaining:
        failed = [m.error for g in sl.groups for m in g.measurements if not m.ok]
        errors = [e for r in sl.rows for e in r.errors]
        if failed:
            raise UiError("build failed:\n" + failed[0].replace(" | ", "\n"))
        raise UiError(errors[0] if errors else "no target could be checked")
    inputs = {"sources": [s.name for s in sources], "entry": entry, "measure": measure,
              "user_flags": list(flags), "defines": defines,
              "description": f"{', '.join(s.name for s in sources)}  entry={entry}"}
    models = sorted({b.cost.trace.unicorn_model for g in sl.groups for b in g.builds if b.ok})
    return report.shortlist_json(sl, inputs, report.versions(tc.version(), ", ".join(models) or None))


class _Handler(BaseHTTPRequestHandler):
    server_version = "mcu-ruleout-ui"
    token = ""
    hosts: tuple[str, ...] = ()

    def log_message(self, *_args) -> None:  # keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                         "connect-src 'self'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed(self, query: dict) -> bool:
        if self.headers.get("Host", "") not in self.hosts:
            return False
        given = self.headers.get("X-Token") or (query.get("token") or [""])[0]
        return secrets.compare_digest(given.encode(), self.token.encode())

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        url = urlparse(self.path)
        if not self._allowed(parse_qs(url.query)):
            self._send(403, b"Open the full address that 'mcu-ruleout ui' printed (it includes a token).",
                       "text/plain; charset=utf-8")
        elif url.path == "/":
            self._send(200, _asset("index.html"), "text/html; charset=utf-8")
        elif url.path == "/api/targets":
            self._json(200, api_targets())
        elif url.path == "/api/examples":
            self._json(200, api_examples())
        elif url.path == "/api/example":
            try:
                self._json(200, api_example((parse_qs(url.query).get("name") or ["fir_f32"])[0]))
            except UiError as e:
                self._json(400, {"error": str(e)})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        routes = {"/api/memory": api_memory, "/api/timing": api_timing, "/api/shortlist": api_shortlist}
        # Read the body before answering, even when refusing. Replying while the client is still
        # sending can reset the connection (seen on Windows), and the client then never sees the reply.
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self.close_connection = True
            self._json(413, {"error": f"request too large (limit {MAX_BODY:,} bytes)"})
            return
        raw = self.rfile.read(length) if length else b""
        if not self._allowed({}):
            self._json(403, {"error": "missing or wrong token"})
            return
        if url.path not in routes:
            self._json(404, {"error": "not found"})
            return
        try:
            if not raw:
                raise UiError("empty request")
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise UiError("expected a JSON object")
            self._json(200, routes[url.path](body))
        except (UiError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - shown to the local user instead of a silent 500
            self._json(500, {"error": f"{type(e).__name__}: {e}"})


def make_server(port: int = 0, token: str | None = None) -> tuple[ThreadingHTTPServer, str]:
    """Create the server (not yet serving). Returns it and the URL to open."""
    token = token or secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", port), type("Handler", (_Handler,), {"token": token}))
    real_port = server.server_address[1]
    server.RequestHandlerClass.hosts = (f"127.0.0.1:{real_port}", f"localhost:{real_port}")
    return server, f"http://127.0.0.1:{real_port}/?token={token}"


def serve(port: int = 8765, open_browser: bool = True, token: str | None = None) -> int:
    server, url = make_server(port, token)
    print(f"mcu-ruleout UI running at:\n  {url}\nIt is reachable from this computer only. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0
