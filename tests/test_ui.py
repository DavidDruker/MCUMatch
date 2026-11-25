"""Web UI server tests: access guards, input validation, and both checks end to end."""
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request

from mcu_ruleout.ui import api_example, make_server

from .helpers import needs_toolchain

HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
TOKEN = "test-token"


class UiServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = make_server(0, TOKEN)
        cls.base = cls.url.split("/?")[0]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path, body=None, token=TOKEN, host=None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Token"] = token
        if host:
            headers["Host"] = host
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            with e:
                raw, status = e.read(), e.code
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw.decode("utf-8", "replace")

    def example(self, **changes):
        ex = api_example()
        return {"target": "nrf52840", "files": ex["files"], "entry": ex["entry"], "measure": ex["measure"],
                "cflags": ex["cflags"], "defines": "", "deadline": "", "deadline_unit": "us", **changes}


class TestAccessGuards(UiServerCase):
    def test_page_and_api_need_the_token(self):
        self.assertEqual(self.call("/", token=None)[0], 403)
        self.assertEqual(self.call("/api/targets", token="wrong")[0], 403)
        self.assertEqual(self.call("/api/memory", body={}, token=None)[0], 403)
        status, page = self.call(f"/?token={TOKEN}", token=None)
        self.assertEqual(status, 200)
        self.assertIn("mcu-ruleout", page)

    def test_foreign_host_header_is_refused(self):
        self.assertEqual(self.call("/api/targets", host="evil.example:80")[0], 403)

    def test_targets_and_example(self):
        status, targets = self.call("/api/targets")
        self.assertEqual(status, 200)
        self.assertEqual({t["id"] for t in targets}, {"rp2040-pico", "nrf52840"})
        self.assertEqual(self.call("/api/example")[0], 200)

    def test_page_never_claims_a_fit(self):
        _, page = self.call(f"/?token={TOKEN}", token=None)
        for phrase in ("will fit", "fits on", "runs in", "meets the deadline."):
            self.assertNotIn(phrase, page.lower())


class TestValidation(UiServerCase):
    def test_bad_requests_get_a_clear_400(self):
        cases = {
            "unknown target": self.example(target="../../etc/passwd"),
            "bad file name": self.example(files=[{"name": "../evil.c", "content": "int x;"}]),
            "is required": self.example(entry=""),
            "plain function name": self.example(entry="a;b"),
            "bad define": self.example(defines="X=$(rm)"),
            "at least one source": self.example(files=[]),
            "no file to compile": self.example(files=[{"name": "only.h", "content": "int x;"}]),
        }
        for needle, body in cases.items():
            with self.subTest(case=needle):
                status, data = self.call("/api/memory", body=body)
                self.assertEqual(status, 400, data)
                self.assertIn(needle, data["error"])

    def test_unknown_route_and_bad_json(self):
        self.assertEqual(self.call("/api/nope", body={})[0], 404)
        req = urllib.request.Request(self.base + "/api/memory", data=b"not json",
                                     headers={"X-Token": TOKEN, "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=30)
        with cm.exception:
            self.assertEqual(cm.exception.code, 400)


@needs_toolchain
class TestChecksEndToEnd(UiServerCase):
    def test_memory_check(self):
        status, d = self.call("/api/memory", body=self.example())
        self.assertEqual(status, 200, d)
        self.assertEqual(d["verdict"], "NOT RULED OUT: measure on hardware")
        self.assertEqual(len(d["measurements"]), 5)
        # x (79 floats) + h (16) + y (64) are static, so they must be counted as RAM
        self.assertGreaterEqual(d["lower_bounds"]["ram_bytes"], (79 + 16 + 64) * 4)

    def test_memory_ruled_out_with_huge_buffer(self):
        files = [{"name": "big.c", "content": "static char b[300000]; int big(void){ for (int i = 0; i < 300000; i++) "
                                               "b[i] = (char)i; return b[7]; }\n"}]
        status, d = self.call("/api/memory", body=self.example(files=files, entry="big", measure=""))
        self.assertEqual(status, 200, d)
        self.assertTrue(d["ruled_out"])
        self.assertIn("RAM", d["reasons"][0])

    def test_compile_error_is_reported_not_crashed(self):
        files = [{"name": "bad.c", "content": "int broken( { return 1; }\n"}]
        status, d = self.call("/api/memory", body=self.example(files=files, entry="broken"))
        self.assertEqual(status, 400)
        self.assertIn("build failed", d["error"])

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_timing_check_and_deadline(self):
        status, d = self.call("/api/timing", body=self.example(deadline="1", deadline_unit="us"))
        self.assertEqual(status, 200, d)
        self.assertEqual(d["verdict"], "RULED OUT (timing, best case)")
        self.assertEqual(list(d["by_function"]), ["fir_f32"])
        self.assertGreater(d["cycles_lower_bound"], d["instructions"])
        status, d = self.call("/api/timing", body=self.example())
        self.assertEqual((status, d["ruled_out"], d["deadline_s"]), (200, False, None))

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_timing_build_error_is_a_400_with_the_compiler_message(self):
        files = [{"name": "bad.c", "content": "void f(void) { undeclared(); }\n"}]
        status, d = self.call("/api/timing", body=self.example(files=files, entry="f", measure="", cflags="-O2 -Werror"))
        self.assertEqual(status, 400)
        self.assertIn("build failed", d["error"])


if __name__ == "__main__":
    unittest.main()
