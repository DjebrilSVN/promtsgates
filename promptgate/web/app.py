from __future__ import annotations
import http.server
import json
import socketserver
import webbrowser
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from promptgate.config import Config


def render_html_dashboard() -> str:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("report.html")

    # Load baselines
    baselines = {}
    for bf in Config.BASELINES_DIR.glob("*_baseline.json"):
        try:
            with open(bf, "r", encoding="utf-8") as f:
                data = json.load(f)
                baselines[bf.stem.replace("_baseline", "")] = data
        except Exception:
            pass

    return template.render(
        baselines=baselines,
        default_model=Config.DEFAULT_TEST_MODEL,
        judge_model=Config.DEFAULT_JUDGE_MODEL
    )


def start_server(port: int = 8000):
    handler = DashboardRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"\n🚀 PromptGate Dashboard running at: {url}")
        print("Press Ctrl+C to stop.\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            html_content = render_html_dashboard().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
        elif self.path == "/api/baselines":
            baselines = {}
            for bf in Config.BASELINES_DIR.glob("*_baseline.json"):
                try:
                    with open(bf, "r", encoding="utf-8") as f:
                        baselines[bf.stem] = json.load(f)
                except Exception:
                    pass
            content = json.dumps(baselines).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            super().do_GET()
