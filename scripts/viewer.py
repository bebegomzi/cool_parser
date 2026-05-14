from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


QUOTE_RE = re.compile(
    r"([^\r\n]{1,80}?님이 보낸글\s*>>\s*"
    r"(\d{4}/\d{2}/\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)"
    r"\s*(?:\([^)]+\))?)"
)


INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>cool_parser 메시지 뷰어</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #20242c;
      --muted: #667085;
      --accent: #136f63;
      --accent-soft: #e2f3ef;
      --danger-soft: #fff1f1;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    header h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    header .count { color: var(--muted); }
    main {
      height: calc(100vh - 56px);
      display: grid;
      grid-template-columns: minmax(360px, 42%) 1fr;
    }
    .left, .right {
      min-width: 0;
      overflow: hidden;
    }
    .left {
      border-right: 1px solid var(--line);
      background: var(--panel);
      display: flex;
      flex-direction: column;
    }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr 104px 104px 92px 84px;
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .check {
      height: 36px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 0 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      white-space: nowrap;
      user-select: none;
    }
    .check input {
      width: 14px;
      height: 14px;
      margin: 0;
    }
    .pager {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }
    .pager button {
      width: 92px;
      background: #fff;
      color: var(--text);
      border-color: var(--line);
      font-weight: 700;
    }
    .pager button:disabled {
      color: #a0a7b2;
      cursor: default;
      background: #f1f3f6;
    }
    .page-info {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    input, select, button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    input { padding: 0 10px; }
    select { padding: 0 8px; }
    button {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 700;
    }
    .results {
      overflow: auto;
    }
    .item {
      width: 100%;
      display: block;
      min-height: 74px;
      padding: 10px 12px;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      text-align: left;
      cursor: pointer;
      overflow: hidden;
    }
    .item.recv {
      background: #fff;
    }
    .item.send {
      background: #fff4c2;
    }
    .item.unread {
      background: #eaf4ff;
      border-left: 5px solid #1f6fbf;
      padding-left: 7px;
    }
    .item.unread:hover, .item.unread.active {
      background: #d9ecff;
    }
    .item:hover, .item.active { background: var(--accent-soft); }
    .meta {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
      overflow: hidden;
      white-space: nowrap;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      height: 20px;
      padding: 0 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      white-space: nowrap;
    }
    .title {
      font-weight: 400;
      line-height: 1.45;
      margin-bottom: 4px;
      word-break: break-word;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
    .item.unread .title {
      font-weight: 700;
    }
    .snippet {
      color: #3f4652;
      line-height: 1.35;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      font-weight: 400;
    }
    .item.unread .snippet {
      font-weight: 700;
    }
    .right {
      display: flex;
      flex-direction: column;
      background: var(--bg);
    }
    .detail-head {
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .detail-title {
      margin: 0 0 10px;
      font-size: 20px;
      line-height: 1.45;
      word-break: break-word;
    }
    .kv {
      display: grid;
      grid-template-columns: 88px 1fr;
      gap: 6px 10px;
      color: var(--muted);
      line-height: 1.5;
    }
    .kv strong { color: var(--text); font-weight: 700; }
    .body {
      padding: 18px;
      overflow: auto;
      line-height: 1.65;
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
      font-size: 15px;
    }
    .thread {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message-part {
      position: relative;
      width: min(76%, 780px);
      border: 1px solid var(--line);
      border-radius: 18px;
      background: #fff;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
    }
    .message-part.sent {
      align-self: flex-end;
      background: #fff2b8;
      border-color: #ead27a;
      border-bottom-right-radius: 7px;
    }
    .message-part.received {
      align-self: flex-start;
      background: #fff;
      border-color: var(--line);
      border-bottom-left-radius: 7px;
    }
    .message-part.sent::after, .message-part.received::after {
      content: "";
      position: absolute;
      bottom: 2px;
      width: 20px;
      height: 18px;
      background: inherit;
      border-bottom: 1px solid;
    }
    .message-part.sent::after {
      right: -13px;
      border-right: 1px solid #ead27a;
      border-bottom-color: #ead27a;
      border-bottom-right-radius: 18px;
      transform: skewX(28deg);
    }
    .message-part.received::after {
      left: -13px;
      border-left: 1px solid var(--line);
      border-bottom-color: var(--line);
      border-bottom-left-radius: 18px;
      transform: skewX(-28deg);
    }
    .part-head {
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.45;
      background: rgba(255, 255, 255, 0.72);
      white-space: pre-wrap;
      word-break: break-word;
      border-top-left-radius: 18px;
      border-top-right-radius: 18px;
    }
    .message-part.sent .part-head {
      border-bottom-color: #ead27a;
      color: #705a00;
    }
    .part-text {
      padding: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .reply-badge {
      background: #fff7df;
      border-color: #efd080;
      color: #6f5200;
    }
    .send-badge {
      background: #fff2b8;
      border-color: #ead27a;
      color: #6f5200;
    }
    .recv-badge {
      background: #fff;
    }
    .unread-badge {
      background: #ffe8e8;
      border-color: #f0a3a3;
      color: #a11d1d;
    }
    .empty {
      padding: 24px;
      color: var(--muted);
    }
    .error {
      margin: 12px;
      padding: 12px;
      border: 1px solid #ffcccc;
      border-radius: 6px;
      background: var(--danger-soft);
      color: #9b1c1c;
    }
    @media (max-width: 820px) {
      main { grid-template-columns: 1fr; grid-template-rows: 48% 52%; }
      .left { border-right: 0; border-bottom: 1px solid var(--line); }
      .toolbar { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>메시지 뷰어</h1>
    <div class="count" id="count">검색어를 입력하세요</div>
  </header>
  <main>
    <section class="left">
      <form class="toolbar" id="searchForm">
        <input id="query" name="q" placeholder="검색어">
        <select id="source" name="source" aria-label="원본">
          <option value="">전체 DB</option>
          <option value="old">예전 DB</option>
          <option value="new">새 DB</option>
        </select>
        <select id="box" name="box" aria-label="보관함">
          <option value="">전체 보관함</option>
          <option value="recv">받은 메시지</option>
          <option value="send">보낸 메시지</option>
        </select>
        <label class="check"><input type="checkbox" name="grouped" value="1" checked>대화 묶기</label>
        <button type="submit">검색</button>
      </form>
      <div class="pager">
        <button type="button" id="prevPage">이전</button>
        <div class="page-info" id="pageInfo">1쪽</div>
        <button type="button" id="nextPage">다음</button>
      </div>
      <div id="results" class="results"></div>
    </section>
    <section class="right" id="detail">
      <div class="empty">왼쪽에서 메시지를 선택하면 본문이 표시됩니다.</div>
    </section>
  </main>
  <script>
    const form = document.querySelector("#searchForm");
    const results = document.querySelector("#results");
    const detail = document.querySelector("#detail");
    const count = document.querySelector("#count");
    const prevPage = document.querySelector("#prevPage");
    const nextPage = document.querySelector("#nextPage");
    const pageInfo = document.querySelector("#pageInfo");
    const pageSize = 100;
    let currentPage = 1;

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    function labelBox(value) {
      return value === "recv" ? "받음" : value === "send" ? "보냄" : value;
    }

    function labelSource(value) {
      return value === "old" ? "예전" : value === "new" ? "새" : value;
    }

    function parseQuoteHeader(header) {
      const match = String(header ?? "").match(/^(.+?)님이 보낸글\\s*>>\\s*(.+)$/);
      if (!match) return { sender: "", date: header };
      return { sender: match[1], date: match[2] };
    }

    function isMine(sender, item) {
      const name = String(sender ?? "").trim();
      if (!name) return item.box === "send";
      return name.includes("정현민");
    }

    function renderMessageBody(item) {
      const text = item.body_text;
      const source = String(text ?? "");
      const marker = /([^\\r\\n]{1,80}?님이 보낸글\\s*>>\\s*\\d{4}\\/\\d{2}\\/\\d{2}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:\\([^)]+\\))?)/g;
      const matches = [...source.matchAll(marker)];
      if (matches.length === 0) {
        const side = item.box === "send" ? "sent" : "received";
        return `
          <div class="thread">
            <section class="message-part ${side}">
              <div class="part-head">현재 메시지</div>
              <div class="part-text">${escapeHtml(source)}</div>
            </section>
          </div>
        `;
      }

      const parts = [];
      const firstText = source.slice(0, matches[0].index).trim();
      parts.push({
        header: "현재 메시지",
        text: firstText,
        side: item.box === "send" ? "sent" : "received"
      });
      for (let i = 0; i < matches.length; i += 1) {
        const match = matches[i];
        const start = match.index;
        const nextStart = i + 1 < matches.length ? matches[i + 1].index : source.length;
        const headerEnd = start + match[0].length;
        const parsed = parseQuoteHeader(match[0]);
        parts.push({
          header: match[0],
          text: source.slice(headerEnd, nextStart).trim(),
          side: isMine(parsed.sender, item) ? "sent" : "received"
        });
      }

      const chronologicalParts = parts.reverse();
      return `<div class="thread">${chronologicalParts.map((part) => {
        return `
          <section class="message-part ${part.side}">
            <div class="part-head">${escapeHtml(part.header)}</div>
            <div class="part-text">${escapeHtml(part.text || "(내용 없음)")}</div>
          </section>
        `;
      }).join("")}</div>`;
    }

    function renderDetailPeople(item) {
      if (item.box === "send") {
        return `
          <strong>받는 사람</strong><span>${escapeHtml(item.receiver || item.person)}</span>
        `;
      }
      return `
        <strong>보낸 사람</strong><span>${escapeHtml(item.sender || item.person)}</span>
        <strong>받은 사람</strong><span>${escapeHtml(item.receiver)}</span>
      `;
    }

    async function searchMessages(event, page = 1) {
      event?.preventDefault();
      currentPage = page;
      const params = new URLSearchParams(new FormData(form));
      params.set("limit", String(pageSize));
      params.set("offset", String((currentPage - 1) * pageSize));
      const response = await fetch(`/api/search?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) {
        results.innerHTML = `<div class="error">${escapeHtml(data.error)}</div>`;
        return;
      }
      count.textContent = `전체 ${data.total.toLocaleString()}건`;
      pageInfo.textContent = `${currentPage}쪽 / ${Math.max(1, Math.ceil(data.total / pageSize))}쪽`;
      prevPage.disabled = currentPage <= 1;
      nextPage.disabled = currentPage * pageSize >= data.total;
      results.innerHTML = data.items.map(item => `
        <button class="item ${item.box} ${item.is_unread ? "unread" : ""}" data-id="${item.id}">
          <div class="meta">
            <span class="badge">${escapeHtml(item.parsed_date)}</span>
            <span class="badge">${labelSource(item.source_db)}</span>
            <span class="badge ${item.box === "send" ? "send-badge" : "recv-badge"}">${labelBox(item.box)}</span>
            ${item.is_unread ? `<span class="badge unread-badge">안 읽음</span>` : ""}
            ${item.has_quote ? `<span class="badge reply-badge">인용</span>` : ""}
            ${item.conversation_count > 1 ? `<span class="badge reply-badge">대화 ${item.conversation_count}</span>` : ""}
            <span>${escapeHtml(item.person)}</span>
          </div>
          <div class="title">${escapeHtml(item.title || "(제목 없음)")}</div>
          <div class="snippet">${escapeHtml(item.snippet)}</div>
        </button>
      `).join("") || `<div class="empty">검색 결과가 없습니다.</div>`;
    }

    async function loadDetail(id) {
      document.querySelectorAll(".item").forEach(el => el.classList.toggle("active", el.dataset.id === id));
      const response = await fetch(`/api/message?id=${encodeURIComponent(id)}`);
      const item = await response.json();
      if (!response.ok) {
        detail.innerHTML = `<div class="error">${escapeHtml(item.error)}</div>`;
        return;
      }
      detail.innerHTML = `
        <div class="detail-head">
          <h2 class="detail-title">${escapeHtml(item.title || "(제목 없음)")}</h2>
          <div class="kv">
            <strong>날짜</strong><span>${escapeHtml(item.date)}</span>
            <strong>원본</strong><span>${escapeHtml(labelSource(item.source_db))} DB / ${escapeHtml(item.source_file)}</span>
            <strong>보관함</strong><span>${escapeHtml(labelBox(item.box))}</span>
            <strong>읽음 상태</strong><span>${item.is_unread ? "안 읽음" : "읽음"}</span>
            ${renderDetailPeople(item)}
            <strong>원래 키</strong><span>${escapeHtml(item.original_key)}</span>
          </div>
        </div>
        <div class="body">${renderMessageBody(item)}</div>
      `;
      const body = detail.querySelector(".body");
      if (body) body.scrollTop = body.scrollHeight;
    }

    results.addEventListener("click", event => {
      const item = event.target.closest(".item");
      if (item) loadDetail(item.dataset.id);
    });
    form.addEventListener("submit", event => searchMessages(event, 1));
    prevPage.addEventListener("click", () => {
      if (currentPage > 1) searchMessages(undefined, currentPage - 1);
    });
    nextPage.addEventListener("click", () => searchMessages(undefined, currentPage + 1));
    document.querySelector("#query").focus();
    searchMessages(undefined, 1);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="통합 메시지 DB를 브라우저에서 보는 로컬 GUI")
    parser.add_argument("--db", type=Path, default=Path("outputs/merged_messages.sqlite"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="시작 후 기본 브라우저를 엽니다.")
    return parser.parse_args()


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def shorten(value: object, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def quote_matches(value: object) -> list[re.Match[str]]:
    return list(QUOTE_RE.finditer(str(value or "")))


def date_minute(value: object) -> str:
    text = str(value or "").strip()
    return text[:16] if len(text) >= 16 else text


def signature_from_row(row: sqlite3.Row) -> tuple[str, str]:
    if row["box"] == "send":
        return ("정현민", date_minute(row["parsed_date"]))
    return (clean_person(row["person"]), date_minute(row["parsed_date"]))


def clean_person(value: object) -> str:
    text = str(value or "").strip().rstrip(";")
    if "(" in text:
        text = text.split("(", 1)[0]
    return text.strip()


def quote_signatures(value: object) -> set[tuple[str, str]]:
    signatures = set()
    for match in quote_matches(value):
        header = match.group(1)
        if "님이 보낸글" not in header:
            continue
        sender = header.split("님이 보낸글", 1)[0].strip()
        signatures.add((sender, date_minute(match.group(2))))
    return signatures


def make_handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, payload: object, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def get_con(self) -> sqlite3.Connection:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            return con

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_html(INDEX_HTML)
            elif parsed.path == "/api/search":
                self.handle_search(parse_qs(parsed.query))
            elif parsed.path == "/api/message":
                self.handle_message(parse_qs(parsed.query))
            else:
                self.send_json({"error": "찾을 수 없는 주소입니다."}, 404)

        def handle_search(self, params: dict[str, list[str]]) -> None:
            query = params.get("q", [""])[0].strip()
            source = params.get("source", [""])[0]
            box = params.get("box", [""])[0]
            limit = min(int(params.get("limit", ["100"])[0]), 300)
            offset = max(int(params.get("offset", ["0"])[0]), 0)
            grouped = params.get("grouped", [""])[0] == "1"

            where = []
            sql_params: dict[str, object] = {"limit": limit, "offset": offset}
            if query:
                where.append(
                    "(title like :query or person like :query or sender like :query "
                    "or receiver like :query or body_text like :query)"
                )
                sql_params["query"] = f"%{query}%"
            if source in {"old", "new"}:
                where.append("source_db = :source")
                sql_params["source"] = source
            if box in {"recv", "send"}:
                where.append("box = :box")
                sql_params["box"] = box

            where_sql = "where " + " and ".join(where) if where else ""
            with self.get_con() as con:
                rows = con.execute(
                    f"""
                    select
                        id, source_db, box, original_key, parsed_date, title, person, body_text,
                        case when box = 'recv' then coalesce(is_unread, 0) else 0 end as is_unread,
                        case when body_text like '%님이 보낸글 >>%' then 1 else 0 end as has_quote
                    from messages
                    {where_sql}
                    order by
                        case when box = 'recv' and coalesce(is_unread, 0) = 1 then 0 else 1 end,
                        parsed_date desc,
                        id desc
                    """,
                    sql_params,
                ).fetchall()
            if grouped:
                rows = self.group_rows(rows)
            total = len(rows)
            rows = rows[offset : offset + limit]
            items = []
            for row in rows:
                item = row_to_dict(row)
                item["snippet"] = shorten(row["body_text"], 90)
                item["conversation_count"] = len(quote_matches(row["body_text"])) + 1
                items.append(item)
            self.send_json({"items": items, "total": total, "limit": limit, "offset": offset})

        def group_rows(self, rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
            grouped_rows = []
            hidden_signatures: set[tuple[str, str]] = set()
            for row in rows:
                sig = signature_from_row(row)
                if sig in hidden_signatures:
                    continue
                grouped_rows.append(row)
                hidden_signatures.update(quote_signatures(row["body_text"]))
            return grouped_rows

        def handle_message(self, params: dict[str, list[str]]) -> None:
            raw_id = params.get("id", [""])[0]
            if not raw_id.isdigit():
                self.send_json({"error": "메시지 ID가 올바르지 않습니다."}, 400)
                return
            with self.get_con() as con:
                row = con.execute("select * from messages where id = ?", (int(raw_id),)).fetchone()
            if row is None:
                self.send_json({"error": "메시지를 찾지 못했습니다."}, 404)
                return
            self.send_json(row_to_dict(row))

    return Handler


def ensure_viewer_schema(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in con.execute("pragma table_info(messages)")}
        if "is_unread" not in columns:
            con.execute("alter table messages add column is_unread integer not null default 0")
            con.commit()
    finally:
        con.close()


def main() -> None:
    args = parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"DB 파일이 없습니다: {db_path}")

    ensure_viewer_schema(db_path)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(db_path))
    url = f"http://{args.host}:{args.port}"
    print(f"메시지 뷰어 실행 중: {url}")
    print("종료하려면 Ctrl+C를 누르세요.")
    if args.open:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
