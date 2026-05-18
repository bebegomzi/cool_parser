from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from merge_messages import merge_sources
from rebuild_udb import rebuild
from run import copy_live_db_to_temp, default_live_dir
from udb_edit import TABLES, append_log, integrity_check, make_backup, table_columns
from viewer import INDEX_HTML, ensure_viewer_schema, make_handler, quote_signatures, signature_from_row


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
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
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
          <div class="actions">
            <button data-action="open" data-kind="${kind}" data-index="${item.index}">열기</button>
            <button class="secondary" data-action="rebuild" data-kind="${kind}" data-index="${item.index}">복구본 만들기</button>
          </div>
        </div>
      `).join("");
    }

    async function openDb(kind, index) {
      setStatus("파싱 중입니다. 메시지가 많으면 잠시 걸릴 수 있습니다.");
      try {
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
      } catch (error) {
        setStatus(`열기에 실패했습니다: ${error}`);
        return;
      }
      setStatus("뷰어를 여는 중입니다.");
      location.href = "/viewer";
    }

    async function rebuildDb(kind, index) {
      setStatus("복구본을 만드는 중입니다. 손상 정도에 따라 잠시 걸릴 수 있습니다.");
      const response = await fetch("/api/rebuild", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind, index})
      });
      const data = await response.json();
      if (!response.ok) {
        setStatus(data.error || "복구본 생성에 실패했습니다.");
        return;
      }
      setStatus(`복구 완료: ${data.output} / 실패 목록: ${data.report}`);
      loadList("input", inputList);
    }

    document.querySelector("#refreshLive").addEventListener("click", () => loadList("live", liveList));
    document.querySelector("#refreshInput").addEventListener("click", () => loadList("input", inputList));
    document.body.addEventListener("click", event => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      if (button.dataset.action === "open") {
        openDb(button.dataset.kind, Number(button.dataset.index));
      } else if (button.dataset.action === "rebuild") {
        rebuildDb(button.dataset.kind, Number(button.dataset.index));
      }
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
    current_label: str | None = None
    current_source: Path | None = None
    current_kind: str | None = None
    editable: bool = False
    live_backup_done: bool = False
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
    state.current_label = None
    state.current_source = None
    state.current_kind = None
    state.editable = False
    state.live_backup_done = False


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
    state.current_label = selected.stem
    state.current_source = selected
    state.current_kind = kind
    state.editable = kind in {"input", "live"}
    return db_path


def refresh_current_view(state: AppState) -> None:
    if state.current_label is None or state.current_source is None:
        raise ValueError("다시 읽을 편집 대상 DB가 없습니다.")
    source = state.current_source
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if state.current_kind == "live":
        temp_dir, source = copy_live_db_to_temp(state.current_source)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    next_work_dir = state.output_dir / f"run_{stamp}"
    try:
        db_path = merge_sources([(state.current_label, source)], next_work_dir)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
    ensure_viewer_schema(db_path)
    state.current_db = db_path
    state.work_dir = next_work_dir


def edit_capabilities(state: AppState) -> dict[str, object]:
    return {
        "editable": state.editable,
        "target": str(state.current_source) if state.editable and state.current_source else "",
        "kind": state.current_kind or "",
        "requires_backup_notice": state.current_kind == "live" and not state.live_backup_done,
    }


def rows_to_delete(ids: list[int], conversation: bool, state: AppState) -> list[sqlite3.Row]:
    if state.current_db is None:
        raise ValueError("먼저 DB를 선택하세요.")
    clean_ids = sorted(set(ids))
    if not clean_ids:
        raise ValueError("삭제할 메시지를 선택하세요.")

    con = sqlite3.connect(state.current_db)
    con.row_factory = sqlite3.Row
    try:
        placeholders = ", ".join("?" for _ in clean_ids)
        selected = con.execute(
            f"select * from messages where id in ({placeholders})",
            clean_ids,
        ).fetchall()
        if len(selected) != len(clean_ids):
            raise ValueError("선택한 메시지 중 일부를 찾지 못했습니다.")
        if not conversation:
            return selected

        wanted = {signature_from_row(row) for row in selected}
        for row in selected:
            wanted.update(quote_signatures(row["body_text"]))
        all_rows = con.execute("select * from messages").fetchall()
        return [row for row in all_rows if signature_from_row(row) in wanted]
    finally:
        con.close()


def delete_selected_messages(ids: list[int], conversation: bool, state: AppState) -> dict[str, object]:
    if not state.editable or state.current_source is None:
        raise ValueError("편집 가능한 DB를 먼저 열어야 합니다.")
    target_rows = rows_to_delete(ids, conversation, state)
    refs = sorted({(str(row["box"]), int(row["original_key"])) for row in target_rows})
    if not refs:
        raise ValueError("삭제할 메시지를 찾지 못했습니다.")

    backup_path = ""
    if state.current_kind == "live" and not state.live_backup_done:
        backup_path = str(make_backup(state.current_source, state.output_dir / "backups"))
        state.live_backup_done = True

    con = sqlite3.connect(state.current_source)
    try:
        con.execute("begin immediate")
        for box, key in refs:
            con.execute(f"delete from {TABLES[box]} where MessageKey = ?", (key,))
        con.commit()
        check = integrity_check(con)
    finally:
        con.close()

    append_log(
        state.output_dir / "edit_log.jsonl",
        {
            "command": "delete-selected",
            "target": str(state.current_source),
            "backup": backup_path,
            "deleted": len(refs),
            "conversation": conversation,
            "refs": [f"{box}:{key}" for box, key in refs],
            "integrity_check": check,
        },
    )
    refresh_current_view(state)
    return {"ok": True, "deleted": len(refs), "backup": backup_path, "integrity_check": check}


def ensure_live_backup(state: AppState) -> str:
    if state.current_kind != "live" or state.current_source is None or state.live_backup_done:
        return ""
    backup_path = str(make_backup(state.current_source, state.output_dir / "backups"))
    state.live_backup_done = True
    return backup_path


def import_source_options(state: AppState) -> list[dict[str, object]]:
    options = []
    for index, path in enumerate(list_udbs("input", state)):
        if state.current_source is not None and path.resolve() == state.current_source.resolve():
            continue
        options.append({"index": index, "name": path.name, "size": format_size(path)})
    return options


def import_all_messages(source_index: int, state: AppState) -> dict[str, object]:
    if not state.editable or state.current_source is None:
        raise ValueError("편집 가능한 DB를 먼저 열어야 합니다.")
    sources = list_udbs("input", state)
    if source_index < 0 or source_index >= len(sources):
        raise ValueError("가져올 DB를 찾지 못했습니다.")
    source_path = sources[source_index]
    if source_path.resolve() == state.current_source.resolve():
        raise ValueError("현재 열려 있는 DB는 가져오기 원본으로 사용할 수 없습니다.")

    backup_path = ensure_live_backup(state)
    imported: dict[str, int] = {}
    source_con = sqlite3.connect(source_path)
    source_con.row_factory = sqlite3.Row
    target_con = sqlite3.connect(state.current_source)
    try:
        target_con.execute("begin immediate")
        for box, table in TABLES.items():
            target_cols = table_columns(target_con, table)
            insert_cols = [col for col in target_cols if col != "MessageKey"]
            placeholders = ", ".join("?" for _ in insert_cols)
            rows = source_con.execute(f"select * from {table} order by MessageKey").fetchall()
            count = 0
            for row in rows:
                target_con.execute(
                    f"insert into {table} ({', '.join(insert_cols)}) values ({placeholders})",
                    [row[col] for col in insert_cols],
                )
                count += 1
            imported[box] = count
        target_con.commit()
        check = integrity_check(target_con)
    except Exception:
        target_con.rollback()
        raise
    finally:
        source_con.close()
        target_con.close()

    append_log(
        state.output_dir / "edit_log.jsonl",
        {
            "command": "import-all",
            "source": str(source_path),
            "target": str(state.current_source),
            "backup": backup_path,
            "imported": imported,
            "integrity_check": check,
        },
    )
    refresh_current_view(state)
    return {
        "ok": True,
        "source": str(source_path),
        "imported": imported,
        "total": sum(imported.values()),
        "backup": backup_path,
        "integrity_check": check,
    }


def rebuild_selected_db(kind: str, index: int, state: AppState) -> tuple[Path, Path]:
    candidates = list_udbs(kind, state)
    if index < 0 or index >= len(candidates):
        raise ValueError("선택한 DB를 찾지 못했습니다.")
    selected = candidates[index]
    source = selected
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if kind == "live":
        temp_dir, source = copy_live_db_to_temp(selected)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = state.output_dir / f"rebuilt_{selected.stem}_{stamp}.udb"
    report_path = state.output_dir / f"rebuilt_{selected.stem}_{stamp}_failed_rows.csv"
    try:
        rebuild(source, output_path, report_path)
        return output_path, report_path
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def make_app_handler(state: AppState):
    viewer_handler = make_handler(
        lambda: state.current_db or Path(""),
        lambda: edit_capabilities(state),
        lambda ids, conversation: delete_selected_messages(ids, conversation, state),
    )

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
            if parsed.path == "/api/import-sources":
                self.send_json({"items": import_source_options(state)})
                return
            if state.current_db is None:
                self.send_json({"error": "먼저 DB를 선택하세요."}, 400)
                return
            super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/delete":
                if state.current_db is None:
                    self.send_json({"error": "먼저 DB를 선택하세요."}, 400)
                    return
                super().do_POST()
                return
            if parsed.path not in {"/api/open", "/api/rebuild", "/api/import-all"}:
                self.send_json({"error": "찾을 수 없는 주소입니다."}, 404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if parsed.path == "/api/import-all":
                try:
                    result = import_all_messages(int(payload.get("source_index", -1)), state)
                except Exception as exc:
                    self.send_json({"error": str(exc)}, 400)
                    return
                self.send_json(result)
                return
            if parsed.path == "/api/rebuild":
                try:
                    output_path, report_path = rebuild_selected_db(
                        str(payload.get("kind", "")),
                        int(payload.get("index", -1)),
                        state,
                    )
                except Exception as exc:
                    self.send_json({"error": str(exc)}, 400)
                    return
                self.send_json({"ok": True, "output": str(output_path), "report": str(report_path)})
                return
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

    server = None
    port = 8765
    for candidate in range(8765, 8780):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), make_app_handler(state))
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("사용 가능한 포트를 찾지 못했습니다. 실행 중인 cool_parser 창을 닫고 다시 시도하세요.")

    url = f"http://127.0.0.1:{port}"
    print(f"cool_parser 실행 중: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        cleanup_state(state)


if __name__ == "__main__":
    main()
