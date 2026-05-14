from __future__ import annotations

import json
import shutil
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from merge_messages import merge_sources
from run import copy_live_db_to_temp, default_live_dir
from viewer import INDEX_HTML, ensure_viewer_schema, make_handler


APP_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>cool_parser 시작</title>
  <style>
    body {
      margin: 0;
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
      background: #f6f7f9;
      color: #20242c;
    }
    main {
      max-width: 860px;
      margin: 0 auto;
      padding: 36px 20px;
    }
    h1 { margin: 0 0 8px; font-size: 28px; }
    p { color: #667085; line-height: 1.6; }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 24px;
    }
    section {
      border: 1px solid #d9dee7;
      border-radius: 10px;
      background: #fff;
      padding: 16px;
    }
    h2 { margin: 0 0 8px; font-size: 18px; }
    button {
      height: 38px;
      padding: 0 12px;
      border: 1px solid #136f63;
      border-radius: 6px;
      background: #136f63;
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }
    .secondary {
      background: #fff;
      color: #20242c;
      border-color: #d9dee7;
    }
    .list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 12px;
    }
    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      background: #fbfcfd;
    }
    .name { word-break: break-all; }
    .muted { color: #667085; font-size: 13px; }
    .status {
      margin-top: 18px;
      padding: 12px;
      border-radius: 8px;
      background: #eef4f2;
      color: #35524c;
      min-height: 22px;
    }
    @media (max-width: 720px) {
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <h1>cool_parser</h1>
    <p>CoolMessenger 메시지 DB를 임시 복사한 뒤 로컬 뷰어로 엽니다. 원본 DB는 수정하지 않습니다.</p>
    <div class="grid">
      <section>
        <h2>현재 CoolMessenger DB</h2>
        <p>사용자 AppData의 Memo 폴더에서 <code>*.udb</code> 파일을 찾습니다.</p>
        <button id="refreshLive">목록 새로고침</button>
        <div class="list" id="liveList"></div>
      </section>
      <section>
        <h2>input 폴더 DB 사본</h2>
        <p>프로그램 폴더의 <code>input</code> 안에 넣은 <code>*.udb</code> 파일을 엽니다.</p>
        <button id="refreshInput" class="secondary">목록 새로고침</button>
        <div class="list" id="inputList"></div>
      </section>
    </div>
    <div class="status" id="status">열 파일을 선택하세요.</div>
  </main>
  <script>
    const statusBox = document.querySelector("#status");
    const liveList = document.querySelector("#liveList");
    const inputList = document.querySelector("#inputList");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    function setStatus(text) {
      statusBox.textContent = text;
    }

    async function loadList(kind, target) {
      target.innerHTML = "";
      const response = await fetch(`/api/list?kind=${kind}`);
      const data = await response.json();
      if (!response.ok) {
        target.innerHTML = `<div class="muted">${escapeHtml(data.error)}</div>`;
        return;
      }
      if (data.items.length === 0) {
        target.innerHTML = `<div class="muted">파일이 없습니다.</div>`;
        return;
      }
      target.innerHTML = data.items.map(item => `
        <div class="row">
          <div>
            <div class="name">${escapeHtml(item.name)}</div>
            <div class="muted">${escapeHtml(item.size)}</div>
          </div>
          <button data-kind="${kind}" data-index="${item.index}">열기</button>
        </div>
      `).join("");
    }

    async function openDb(kind, index) {
      setStatus("파싱 중입니다. 메시지가 많으면 잠시 걸릴 수 있습니다.");
      const response = await fetch("/api/open", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind, index})
      });
      const data = await response.json();
      if (!response.ok) {
        setStatus(data.error || "열기에 실패했습니다.");
        return;
      }
      setStatus("뷰어를 여는 중입니다.");
      location.href = "/viewer";
    }

    document.querySelector("#refreshLive").addEventListener("click", () => loadList("live", liveList));
    document.querySelector("#refreshInput").addEventListener("click", () => loadList("input", inputList));
    document.body.addEventListener("click", event => {
      const button = event.target.closest("button[data-kind]");
      if (button) openDb(button.dataset.kind, Number(button.dataset.index));
    });
    loadList("live", liveList);
    loadList("input", inputList);
  </script>
</body>
</html>
"""


@dataclass
class AppState:
    root_dir: Path
    output_dir: Path
    current_db: Path | None = None
    temp_live_dir: tempfile.TemporaryDirectory[str] | None = None
    work_dir: Path | None = None


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def format_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def list_udbs(kind: str, state: AppState) -> list[Path]:
    if kind == "live":
        folder = default_live_dir()
    elif kind == "input":
        folder = state.root_dir / "input"
        folder.mkdir(exist_ok=True)
    else:
        raise ValueError("지원하지 않는 목록입니다.")
    if not folder.exists():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".udb")


def cleanup_state(state: AppState) -> None:
    if state.temp_live_dir is not None:
        state.temp_live_dir.cleanup()
        state.temp_live_dir = None
    if state.work_dir is not None and state.work_dir.exists():
        shutil.rmtree(state.work_dir, ignore_errors=True)
        state.work_dir = None
    state.current_db = None


def open_selected_db(kind: str, index: int, state: AppState) -> Path:
    candidates = list_udbs(kind, state)
    if index < 0 or index >= len(candidates):
        raise ValueError("선택한 DB를 찾지 못했습니다.")

    cleanup_state(state)
    selected = candidates[index]
    source = selected
    if kind == "live":
        state.temp_live_dir, source = copy_live_db_to_temp(selected)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    state.work_dir = state.output_dir / f"run_{stamp}"
    db_path = merge_sources([(selected.stem, source)], state.work_dir)
    ensure_viewer_schema(db_path)
    state.current_db = db_path
    return db_path


def make_app_handler(state: AppState):
    viewer_handler = make_handler(lambda: state.current_db or Path(""))

    class AppHandler(viewer_handler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_html(APP_HTML)
                return
            if parsed.path == "/viewer":
                if state.current_db is None:
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.end_headers()
                    return
                self.send_html(INDEX_HTML)
                return
            if parsed.path == "/api/list":
                self.handle_list(parse_qs(parsed.query))
                return
            if state.current_db is None:
                self.send_json({"error": "먼저 DB를 선택하세요."}, 400)
                return
            super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/open":
                self.send_json({"error": "찾을 수 없는 주소입니다."}, 404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            try:
                db_path = open_selected_db(str(payload.get("kind", "")), int(payload.get("index", -1)), state)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            self.send_json({"ok": True, "db": str(db_path)})

        def handle_list(self, params: dict[str, list[str]]) -> None:
            kind = params.get("kind", [""])[0]
            try:
                paths = list_udbs(kind, state)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            self.send_json(
                {
                    "items": [
                        {"index": index, "name": path.name, "size": format_size(path)}
                        for index, path in enumerate(paths)
                    ]
                }
            )

    return AppHandler


def main() -> None:
    root_dir = app_root()
    state = AppState(root_dir=root_dir, output_dir=root_dir / "output")
    (root_dir / "input").mkdir(exist_ok=True)
    state.output_dir.mkdir(exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", 8765), make_app_handler(state))
    url = "http://127.0.0.1:8765"
    print(f"cool_parser 실행 중: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        cleanup_state(state)


if __name__ == "__main__":
    main()
