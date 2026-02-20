#!/usr/bin/env python3
import html
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = ROOT / "easy-clip.sh"
OUTPUT_ROOT = ROOT / "web_outputs"
STATIC_ROOT = ROOT / "web_static"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
STATIC_ROOT.mkdir(parents=True, exist_ok=True)


def is_hhmmss(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 3 or any(len(p) != 2 or not p.isdigit() for p in parts):
        return False
    hh, mm, ss = map(int, parts)
    return hh >= 0 and 0 <= mm <= 59 and 0 <= ss <= 59


def to_seconds(hhmmss: str) -> int:
    hh, mm, ss = map(int, hhmmss.split(":"))
    return hh * 3600 + mm * 60 + ss


def parse_segments(text: str) -> list[tuple[str, str]]:
    segments = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Timestamp wajib diisi minimal 1 baris")

    for idx, line in enumerate(lines, start=1):
        parts = [x for x in line.replace("-", " ").split() if x]
        if len(parts) != 2:
            raise ValueError(f"Format baris {idx} salah. Gunakan: HH:MM:SS HH:MM:SS")

        start, end = parts
        if not is_hhmmss(start) or not is_hhmmss(end):
            raise ValueError(f"Format waktu baris {idx} harus HH:MM:SS")

        if to_seconds(end) <= to_seconds(start):
            raise ValueError(f"Baris {idx}: end time harus lebih besar dari start time")

        segments.append((start, end))

    return segments


def render_page(error: str = "", success: str = "", items: list | None = None, form: dict | None = None) -> str:
    form = form or {}
    source = html.escape(form.get("source_url", ""))
    timestamps = html.escape(form.get("timestamps", ""))
    mode = form.get("mode", "both")

    error_html = f'<div class="alert error">{html.escape(error)}</div>' if error else ""
    success_html = f'<div class="alert success">{html.escape(success)}</div>' if success else ""

    def active(value: str) -> str:
        return "active" if mode == value else ""

    result_html = ""
    if items:
        cards = []
        for item in items:
            seg_label = html.escape(item["label"])
            inner = ""
            if item.get("horizontal"):
                h = html.escape(item["horizontal"])
                inner += f"""
                <div>
                  <h4>Horizontal</h4>
                  <video controls src=\"{h}\"></video>
                  <p><a href=\"{h}\" download>Download horizontal</a></p>
                </div>
                """
            if item.get("vertical"):
                v = html.escape(item["vertical"])
                inner += f"""
                <div>
                  <h4>Vertical 9:16</h4>
                  <video controls src=\"{v}\"></video>
                  <p><a href=\"{v}\" download>Download vertical</a></p>
                </div>
                """

            cards.append(
                f"""
                <section class=\"card\">
                  <h3>{seg_label}</h3>
                  <div class=\"result-grid\">{inner}</div>
                </section>
                """
            )

        result_html = "<section><h2>Preview Hasil</h2>" + "".join(cards) + "</section>"

    return f"""<!doctype html>
<html lang=\"id\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Easy-clip Web</title>
  <link rel=\"stylesheet\" href=\"/static/styles.css\" />
</head>
<body>
  <main class=\"container\">
    <h1>Easy-clip</h1>
    <p class=\"subtitle\">Input banyak timestamp (satu baris satu clip): <code>HH:MM:SS HH:MM:SS</code></p>

    <section class=\"card\">
      <form method=\"post\" action=\"/clip\">
        <label for=\"source_url\">Link video (YouTube / MP4)</label>
        <input id=\"source_url\" name=\"source_url\" placeholder=\"https://...\" value=\"{source}\" required />

        <label for=\"timestamps\">Multiple Timestamp</label>
        <textarea id=\"timestamps\" name=\"timestamps\" rows=\"6\" placeholder=\"00:00:05 00:00:15&#10;00:01:00 00:01:25\" required>{timestamps}</textarea>

        <p class=\"hint\">Contoh format per baris: <strong>start end</strong> atau <strong>start-end</strong>.</p>

        <div class=\"button-row\">
          <button class=\"{active('horizontal')}\" type=\"submit\" name=\"mode\" value=\"horizontal\">Generate Horizontal</button>
          <button class=\"{active('vertical')}\" type=\"submit\" name=\"mode\" value=\"vertical\">Generate Vertical 9:16</button>
          <button class=\"{active('both')}\" type=\"submit\" name=\"mode\" value=\"both\">Generate Both</button>
        </div>
      </form>
    </section>

    {error_html}
    {success_html}
    {result_html}
  </main>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send_html(render_page())
            return

        if self.path.startswith("/static/"):
            self._serve_file(STATIC_ROOT, self.path.removeprefix("/static/"))
            return

        if self.path.startswith("/outputs/"):
            self._serve_file(OUTPUT_ROOT, self.path.removeprefix("/outputs/"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path != "/clip":
            self.send_error(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        data = {k: v[0] for k, v in parse_qs(body).items()}

        source = data.get("source_url", "").strip()
        timestamp_text = data.get("timestamps", "").strip()
        mode = data.get("mode", "both").strip().lower()

        if mode not in {"horizontal", "vertical", "both"}:
            mode = "both"
        data["mode"] = mode

        if not source:
            self._send_html(render_page(error="Link video wajib diisi", form=data), status=400)
            return

        try:
            segments = parse_segments(timestamp_text)
        except ValueError as exc:
            self._send_html(render_page(error=str(exc), form=data), status=400)
            return

        job_id = uuid.uuid4().hex
        job_dir = OUTPUT_ROOT / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        items = []
        for idx, (start, end) in enumerate(segments, start=1):
            outdir = job_dir / f"segment-{idx:02d}"
            outdir.mkdir(parents=True, exist_ok=True)

            cmd = [
                str(SCRIPT_PATH),
                "--input",
                source,
                "--start",
                start,
                "--end",
                end,
                "--outdir",
                str(outdir),
            ]

            proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            if proc.returncode != 0:
                error = proc.stderr.strip() or proc.stdout.strip() or f"Gagal membuat clip segment {idx}"
                self._send_html(render_page(error=error, form=data), status=500)
                return

            horizontal = f"/outputs/{job_id}/segment-{idx:02d}/clip-horizontal.mp4"
            vertical = f"/outputs/{job_id}/segment-{idx:02d}/clip-vertical-9x16.mp4"
            items.append(
                {
                    "label": f"Segment {idx}: {start} - {end}",
                    "horizontal": horizontal if mode in {"horizontal", "both"} else "",
                    "vertical": vertical if mode in {"vertical", "both"} else "",
                }
            )

        success = f"Berhasil generate {len(items)} clip ({mode})"
        self._send_html(render_page(success=success, items=items, form=data))

    def _serve_file(self, base: Path, rel_path: str):
        rel = Path(rel_path.lstrip("/"))
        target = (base / rel).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.exists() or not target.is_file():
            self.send_error(404, "File not found")
            return

        mime = "application/octet-stream"
        suffix = target.suffix.lower()
        if suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif suffix == ".mp4":
            mime = "video/mp4"

        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_html(self, html_text: str, status: int = 200):
        encoded = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args):
        return


if __name__ == "__main__":
    print(f"Easy-clip web running at http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()
