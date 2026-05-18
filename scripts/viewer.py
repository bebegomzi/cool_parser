from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import html
import json
import re
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
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
      grid-template-columns: 1fr 104px 104px 92px 92px 84px;
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .datebar {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
      padding: 0 12px 12px;
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
    .editbar {
      display: none;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
      background: #f8fbff;
    }
    .editbar.show { display: flex; }
    .editbar button {
      width: auto;
      padding: 0 10px;
    }
    .editbar select {
      min-width: 160px;
      max-width: 240px;
    }
    .editbar .secondary {
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .editbar .danger {
      background: #c93838;
      border-color: #c93838;
    }
    .editbar .danger:disabled {
      background: #e4e7ec;
      border-color: #e4e7ec;
      color: #98a2b3;
      cursor: default;
    }
    .edit-note {
      color: var(--muted);
      font-size: 13px;
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
      display: grid;
      grid-template-columns: 1fr;
      gap: 0;
      min-height: 74px;
      padding: 11px 12px;
      border: 1px solid transparent;
      border-bottom-color: var(--line);
      background: #fff;
      color: var(--text);
      text-align: left;
      cursor: pointer;
      overflow: hidden;
    }
    .item.selecting {
      grid-template-columns: 24px 1fr;
      gap: 8px;
      align-items: start;
    }
    .select-check {
      width: 16px;
      height: 16px;
      margin-top: 4px;
    }
    .item.recv {
      background: #fff;
    }
    .item.send {
      background: #fff4c2;
    }
    .item:hover {
      border-color: #aac9e8;
    }
    .item.active {
      border-color: #1f6fbf;
      border-left-width: 5px;
      padding-left: 8px;
      box-shadow: inset 0 0 0 1px #1f6fbf;
    }
    .item.multi-selected {
      border-color: #1f6fbf;
      box-shadow: inset 0 0 0 2px #1f6fbf;
    }
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
      line-height: 1.45;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
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
    mark {
      background: #b9f6ca;
      color: inherit;
      padding: 0 2px;
      border-radius: 3px;
    }
    .attachments {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .attachment-wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .attachment-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .attachment {
      min-height: 26px;
      padding: 3px 8px;
      border: 1px solid #8fc5a6;
      border-radius: 999px;
      background: #eefaf2;
      color: #145c32;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    .attachment:hover {
      background: #dff4e8;
    }
    .toast {
      position: fixed;
      left: 0;
      top: 0;
      z-index: 10;
      padding: 10px 14px;
      border-radius: 8px;
      background: #1f6f3d;
      color: #fff;
      box-shadow: 0 8px 24px rgba(16, 24, 40, 0.18);
      opacity: 0;
      transform: translateY(8px);
      pointer-events: none;
      transition: opacity 0.18s ease, transform 0.18s ease;
    }
    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(15, 23, 42, 0.34);
      z-index: 20;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
      width: min(420px, 100%);
      padding: 18px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #fff;
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18);
    }
    .modal h2 {
      margin: 0 0 10px;
      font-size: 18px;
    }
    .modal p {
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.5;
    }
    .modal label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 16px;
    }
    .modal-actions .secondary {
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .attach-badge {
      background: #eefaf2;
      border-color: #8fc5a6;
      color: #145c32;
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
      .datebar { grid-template-columns: 1fr; }
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
        <label class="check"><input type="checkbox" name="has_attachment" value="1">첨부 있음</label>
        <button type="submit">검색</button>
        <div class="datebar">
          <select id="yearFilter" name="year" aria-label="연도">
            <option value="">전체 연도</option>
          </select>
          <select name="month" aria-label="월">
            <option value="">전체 월</option>
            <option value="01">1월</option>
            <option value="02">2월</option>
            <option value="03">3월</option>
            <option value="04">4월</option>
            <option value="05">5월</option>
            <option value="06">6월</option>
            <option value="07">7월</option>
            <option value="08">8월</option>
            <option value="09">9월</option>
            <option value="10">10월</option>
            <option value="11">11월</option>
            <option value="12">12월</option>
          </select>
          <select name="period" aria-label="기간">
            <option value="">전체 기간</option>
            <option value="today">오늘</option>
            <option value="last7">최근 7일</option>
            <option value="this_month">이번 달</option>
            <option value="last_month">지난 달</option>
            <option value="this_year">올해</option>
          </select>
        </div>
      </form>
      <div class="pager">
        <button type="button" id="prevPage">이전</button>
        <div class="page-info" id="pageInfo">1쪽</div>
        <button type="button" id="nextPage">다음</button>
      </div>
      <div class="editbar" id="editBar">
        <button type="button" class="secondary" id="toggleSelect">선택 모드</button>
        <button type="button" class="danger" id="deleteSelected" disabled>선택 삭제</button>
        <select id="importSource" aria-label="가져올 DB">
          <option value="">가져올 DB</option>
        </select>
        <button type="button" class="secondary" id="importAll" disabled>전체 가져오기</button>
        <span class="edit-note" id="editNote">input DB를 열었을 때만 삭제할 수 있습니다.</span>
      </div>
      <div id="results" class="results"></div>
    </section>
    <section class="right" id="detail">
      <div class="empty">왼쪽에서 메시지를 선택하면 본문이 표시됩니다.</div>
    </section>
  </main>
  <div class="toast" id="toast"></div>
  <div class="modal-backdrop" id="deleteModal">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="deleteModalTitle">
      <h2 id="deleteModalTitle">메시지 삭제</h2>
      <p id="deleteModalText"></p>
      <label><input type="checkbox" id="skipDeleteConfirm"> 다시 묻지 않음</label>
      <div class="modal-actions">
        <button type="button" class="secondary" id="cancelDelete">아니오</button>
        <button type="button" class="danger" id="confirmDelete">예, 삭제</button>
      </div>
    </div>
  </div>
  <script>
    const form = document.querySelector("#searchForm");
    const results = document.querySelector("#results");
    const detail = document.querySelector("#detail");
    const count = document.querySelector("#count");
    const prevPage = document.querySelector("#prevPage");
    const nextPage = document.querySelector("#nextPage");
    const pageInfo = document.querySelector("#pageInfo");
    const yearFilter = document.querySelector("#yearFilter");
    const toast = document.querySelector("#toast");
    const editBar = document.querySelector("#editBar");
    const toggleSelect = document.querySelector("#toggleSelect");
    const deleteSelected = document.querySelector("#deleteSelected");
    const editNote = document.querySelector("#editNote");
    const deleteModal = document.querySelector("#deleteModal");
    const deleteModalText = document.querySelector("#deleteModalText");
    const skipDeleteConfirm = document.querySelector("#skipDeleteConfirm");
    const cancelDelete = document.querySelector("#cancelDelete");
    const confirmDelete = document.querySelector("#confirmDelete");
    const importSource = document.querySelector("#importSource");
    const importAll = document.querySelector("#importAll");
    const pageSize = 100;
    let currentPage = 1;
    let currentKeywords = [];
    let canEdit = false;
    let requiresBackupNotice = false;
    let selecting = false;
    let activeId = "";
    let anchorId = "";
    let deleteConfirmedOnce = false;
    const checkedIds = new Set();

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }

    function escapeRegExp(value) {
      return String(value).replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&");
    }

    function highlight(value) {
      let text = escapeHtml(value);
      const keywords = [...new Set(currentKeywords.filter(Boolean))].sort((a, b) => b.length - a.length);
      for (const keyword of keywords) {
        const pattern = new RegExp(escapeRegExp(escapeHtml(keyword)), "gi");
        text = text.replace(pattern, match => `<mark>${match}</mark>`);
      }
      return text;
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

    function timeFromDate(value) {
      const match = String(value ?? "").match(/\\b(\\d{1,2}:\\d{2})(?::\\d{2})?/);
      return match ? match[1] : "";
    }

    function cleanDisplayName(value) {
      let text = String(value ?? "").trim().replace(/;+$/, "");
      const match = text.match(/^(.+?)\\(/);
      if (match) text = match[1];
      return text.trim();
    }

    function currentHeader(item) {
      const who = item.box === "send" ? "나" : cleanDisplayName(item.sender || item.person);
      const time = timeFromDate(item.date || item.parsed_date);
      return `현재 메시지(${who || "알 수 없음"})${time ? " " + time : ""}`;
    }

    let toastTimer = null;
    function showToast(message, anchor) {
      const rect = anchor?.getBoundingClientRect?.();
      toast.textContent = message;
      if (rect) {
        toast.style.left = `${Math.min(rect.left, window.innerWidth - 210)}px`;
        toast.style.top = `${Math.max(8, rect.top - 44)}px`;
      }
      toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove("show"), 1600);
    }

    async function copyText(value, anchor) {
      try {
        await navigator.clipboard.writeText(value);
        showToast("파일명을 복사했습니다.", anchor);
      } catch {
        showToast("복사에 실패했습니다.", anchor);
      }
    }

    function updateDeleteButton() {
      const count = checkedIds.size || (activeId ? 1 : 0);
      deleteSelected.disabled = count === 0;
      deleteSelected.textContent = checkedIds.size ? `선택 삭제 (${checkedIds.size})` : "현재 삭제";
    }

    function visibleItemIds() {
      return [...results.querySelectorAll(".item")].map(item => String(item.dataset.id));
    }

    function syncSelectionStyles() {
      document.querySelectorAll(".item").forEach(item => {
        const selected = checkedIds.has(String(item.dataset.id));
        item.classList.toggle("multi-selected", selected);
        const checkbox = item.querySelector(".select-check");
        if (checkbox) checkbox.checked = selected;
      });
      updateDeleteButton();
    }

    function toggleChecked(id) {
      if (checkedIds.has(id)) checkedIds.delete(id);
      else checkedIds.add(id);
      anchorId = id;
      syncSelectionStyles();
    }

    function selectRange(toId) {
      const ids = visibleItemIds();
      const from = ids.indexOf(anchorId || activeId || toId);
      const to = ids.indexOf(toId);
      if (from === -1 || to === -1) {
        checkedIds.add(toId);
        anchorId = toId;
        syncSelectionStyles();
        return;
      }
      const [start, end] = from <= to ? [from, to] : [to, from];
      for (const id of ids.slice(start, end + 1)) checkedIds.add(id);
      anchorId = toId;
      syncSelectionStyles();
    }

    async function loadCapabilities() {
      const response = await fetch("/api/capabilities");
      const data = await response.json();
      canEdit = Boolean(data.editable);
      requiresBackupNotice = Boolean(data.requires_backup_notice);
      editBar.classList.toggle("show", canEdit);
      if (data.target) {
        editNote.textContent = requiresBackupNotice
          ? `편집 대상: ${data.target} / 첫 수정 때 백업을 만듭니다.`
          : `편집 대상: ${data.target}`;
      } else {
        editNote.textContent = "편집 가능한 DB를 열었을 때만 삭제할 수 있습니다.";
      }
    }

    async function loadImportSources() {
      if (!canEdit) return;
      const response = await fetch("/api/import-sources");
      const data = await response.json();
      if (!response.ok) return;
      importSource.innerHTML = `<option value="">가져올 DB</option>` + data.items.map(item => (
        `<option value="${escapeHtml(item.index)}">${escapeHtml(item.name)} (${escapeHtml(item.size)})</option>`
      )).join("");
      importAll.disabled = importSource.value === "";
    }

    function askDeleteConfirm(ids) {
      return new Promise(resolve => {
        const backupText = requiresBackupNotice ? " 현재 DB를 직접 수정하므로, 첫 수정 전에 백업을 만듭니다." : "";
        deleteModalText.textContent = `선택한 ${ids.length}개 메시지를 삭제할까요? 대화로 묶인 메시지는 가능한 범위에서 함께 삭제합니다.${backupText}`;
        deleteModal.classList.add("show");
        confirmDelete.focus();

        const close = result => {
          deleteModal.classList.remove("show");
          cancelDelete.removeEventListener("click", onCancel);
          confirmDelete.removeEventListener("click", onConfirm);
          deleteModal.removeEventListener("click", onBackdrop);
          document.removeEventListener("keydown", onKey);
          resolve(result);
        };
        const onCancel = () => close(false);
        const onConfirm = () => close(true);
        const onBackdrop = event => {
          if (event.target === deleteModal) close(false);
        };
        const onKey = event => {
          if (event.key === "Escape") close(false);
        };
        cancelDelete.addEventListener("click", onCancel);
        confirmDelete.addEventListener("click", onConfirm);
        deleteModal.addEventListener("click", onBackdrop);
        document.addEventListener("keydown", onKey);
      });
    }

    function renderAttachments(value) {
      const names = String(value ?? "").split(";").map(name => name.trim()).filter(Boolean);
      if (names.length === 0) return "";
      return `
        <strong>첨부파일</strong>
        <span class="attachment-wrap">
          <span class="attachments">
            ${names.map(name => `
              <button type="button" class="attachment" data-copy="${escapeHtml(name)}">${highlight(name)}</button>
            `).join("")}
          </span>
          <span class="attachment-note">다운로드는 불가하며 클릭 시 파일명을 복사합니다.</span>
        </span>
      `;
    }

    function isMine(sender, item) {
      const name = String(sender ?? "").trim();
      if (!name) return item.box === "send";
      return item.owner_name && name.includes(item.owner_name);
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
              <div class="part-head">${escapeHtml(currentHeader(item))}</div>
              <div class="part-text">${highlight(source)}</div>
            </section>
          </div>
        `;
      }

      const parts = [];
      const firstText = source.slice(0, matches[0].index).trim();
      parts.push({
        header: currentHeader(item),
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
            <div class="part-head">${highlight(part.header)}</div>
            <div class="part-text">${highlight(part.text || "(내용 없음)")}</div>
          </section>
        `;
      }).join("")}</div>`;
    }

    function renderDetailPeople(item) {
      if (item.box === "send") {
        return `
          <strong>받는 사람</strong><span>${highlight(item.receiver || item.person)}</span>
        `;
      }
      return `
        <strong>보낸 사람</strong><span>${highlight(item.sender || item.person)}</span>
        <strong>받은 사람</strong><span>${highlight(item.receiver)}</span>
      `;
    }

    async function searchMessages(event, page = 1) {
      event?.preventDefault();
      currentPage = page;
      const params = new URLSearchParams(new FormData(form));
      currentKeywords = String(params.get("q") ?? "").trim().split(/\\s+/).filter(Boolean);
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
        <button class="item ${item.box} ${item.is_unread ? "unread" : ""} ${selecting ? "selecting" : ""} ${checkedIds.has(String(item.id)) ? "multi-selected" : ""}" data-id="${item.id}">
          ${selecting ? `<input class="select-check" type="checkbox" ${checkedIds.has(String(item.id)) ? "checked" : ""}>` : ""}
          <div>
            <div class="meta">
              <span class="badge">${escapeHtml(item.parsed_date)}</span>
              <span class="badge">${labelSource(item.source_db)}</span>
              <span class="badge ${item.box === "send" ? "send-badge" : "recv-badge"}">${labelBox(item.box)}</span>
              ${item.is_unread ? `<span class="badge unread-badge">안 읽음</span>` : ""}
              ${item.has_quote ? `<span class="badge reply-badge">인용</span>` : ""}
              ${item.conversation_count > 1 ? `<span class="badge reply-badge">대화 ${item.conversation_count}</span>` : ""}
              ${item.has_attachment ? `<span class="badge attach-badge">첨부</span>` : ""}
              <span>${highlight(item.person)}</span>
            </div>
            <div class="snippet">${highlight(item.snippet || item.title || "(내용 없음)")}</div>
          </div>
        </button>
      `).join("") || `<div class="empty">검색 결과가 없습니다.</div>`;
      syncSelectionStyles();
    }

    async function loadDetail(id) {
      activeId = String(id);
      anchorId = activeId;
      document.querySelectorAll(".item").forEach(el => el.classList.toggle("active", el.dataset.id === id));
      const response = await fetch(`/api/message?id=${encodeURIComponent(id)}`);
      const item = await response.json();
      if (!response.ok) {
        detail.innerHTML = `<div class="error">${escapeHtml(item.error)}</div>`;
        return;
      }
      detail.innerHTML = `
        <div class="detail-head">
          <h2 class="detail-title">${highlight(item.title || "(제목 없음)")}</h2>
          <div class="kv">
            <strong>날짜</strong><span>${escapeHtml(item.date)}</span>
            <strong>원본</strong><span>${escapeHtml(labelSource(item.source_db))} DB / ${escapeHtml(item.source_file)}</span>
            <strong>보관함</strong><span>${escapeHtml(labelBox(item.box))}</span>
            <strong>읽음 상태</strong><span>${item.is_unread ? "안 읽음" : "읽음"}</span>
            ${renderDetailPeople(item)}
            ${renderAttachments(item.attachment_names)}
          </div>
        </div>
        <div class="body">${renderMessageBody(item)}</div>
      `;
      const body = detail.querySelector(".body");
      if (body) body.scrollTop = body.scrollHeight;
      updateDeleteButton();
    }

    async function loadYears() {
      const response = await fetch("/api/years");
      const data = await response.json();
      if (!response.ok) return;
      yearFilter.innerHTML = `<option value="">전체 연도</option>` + data.years.map(year => (
        `<option value="${escapeHtml(year)}">${escapeHtml(year)}년</option>`
      )).join("");
    }

    results.addEventListener("click", event => {
      const item = event.target.closest(".item");
      if (!item) return;
      const id = String(item.dataset.id);
      if (event.shiftKey) {
        selectRange(id);
        if (!selecting) loadDetail(id);
        return;
      }
      if (event.ctrlKey || event.metaKey || selecting) {
        toggleChecked(id);
        return;
      }
      if (checkedIds.size) {
        checkedIds.clear();
        syncSelectionStyles();
      }
      loadDetail(id);
    });
    toggleSelect.addEventListener("click", () => {
      selecting = !selecting;
      checkedIds.clear();
      anchorId = activeId;
      toggleSelect.textContent = selecting ? "선택 취소" : "선택 모드";
      searchMessages(undefined, currentPage);
    });
    async function deleteCurrentSelection() {
      if (!canEdit) return;
      const ids = checkedIds.size ? [...checkedIds] : (activeId ? [activeId] : []);
      if (ids.length === 0) return;
      const shouldConfirm = !skipDeleteConfirm.checked || !deleteConfirmedOnce;
      if (shouldConfirm) {
        const ok = await askDeleteConfirm(ids);
        if (!ok) return;
        deleteConfirmedOnce = true;
      }
      const response = await fetch("/api/delete", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ids, conversation: true})
      });
      const data = await response.json();
      if (!response.ok) {
        showToast(data.error || "삭제에 실패했습니다.", deleteSelected);
        return;
      }
      if (data.backup) {
        requiresBackupNotice = false;
        editNote.textContent = `편집 대상 백업 생성됨: ${data.backup}`;
      }
      showToast(`${data.deleted}건 삭제 완료`, deleteSelected);
      checkedIds.clear();
      activeId = "";
      anchorId = "";
      selecting = false;
      toggleSelect.textContent = "선택 모드";
      detail.innerHTML = `<div class="empty">왼쪽에서 메시지를 선택하면 본문이 표시됩니다.</div>`;
      await loadYears();
      await searchMessages(undefined, 1);
    }
    deleteSelected.addEventListener("click", deleteCurrentSelection);
    importSource.addEventListener("change", () => {
      importAll.disabled = importSource.value === "";
    });
    importAll.addEventListener("click", async () => {
      if (!canEdit || importSource.value === "") return;
      const selectedName = importSource.options[importSource.selectedIndex]?.textContent || "선택한 DB";
      const backupText = requiresBackupNotice ? "\\n\\n현재 DB를 직접 수정하므로, 첫 수정 전에 백업을 만듭니다." : "";
      const ok = confirm(`${selectedName}의 받은 메시지와 보낸 메시지를 모두 현재 DB로 가져올까요?${backupText}`);
      if (!ok) return;
      importAll.disabled = true;
      showToast("가져오는 중입니다.", importAll);
      const response = await fetch("/api/import-all", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source_index: Number(importSource.value)})
      });
      const data = await response.json();
      importAll.disabled = importSource.value === "";
      if (!response.ok) {
        showToast(data.error || "가져오기에 실패했습니다.", importAll);
        return;
      }
      if (data.backup) requiresBackupNotice = false;
      showToast(`${data.total}건 가져오기 완료`, importAll);
      detail.innerHTML = `<div class="empty">왼쪽에서 메시지를 선택하면 본문이 표시됩니다.</div>`;
      activeId = "";
      anchorId = "";
      await loadYears();
      await searchMessages(undefined, 1);
    });
    document.addEventListener("keydown", event => {
      const tagName = String(event.target?.tagName ?? "").toLowerCase();
      if (tagName === "input" || tagName === "textarea" || tagName === "select") return;
      if (event.key !== "Delete" && event.key !== "Del") return;
      if (!canEdit) return;
      event.preventDefault();
      deleteCurrentSelection();
    });
    detail.addEventListener("click", event => {
      const attachment = event.target.closest(".attachment");
      if (attachment) copyText(attachment.dataset.copy, attachment);
    });
    form.addEventListener("submit", event => searchMessages(event, 1));
    prevPage.addEventListener("click", () => {
      if (currentPage > 1) searchMessages(undefined, currentPage - 1);
    });
    nextPage.addEventListener("click", () => searchMessages(undefined, currentPage + 1));
    document.querySelector("#query").focus();
    loadCapabilities().then(loadImportSources);
    loadYears();
    searchMessages(undefined, 1);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="통합 메시지 DB를 브라우저에서 보는 로컬 GUI")
    parser.add_argument("--db", type=Path, default=Path("output/merged_messages.sqlite"))
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


def owner_name_from_source_file(value: object) -> str:
    name = Path(str(value or "")).stem
    if "(" in name:
        name = name.split("(", 1)[0]
    return name.strip()


def signature_from_row(row: sqlite3.Row) -> tuple[str, str]:
    if row["box"] == "send":
        return (owner_name_from_source_file(row["source_file"]), date_minute(row["parsed_date"]))
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


def make_handler(
    db_path: Path | Callable[[], Path],
    capabilities: Callable[[], dict[str, object]] | None = None,
    delete_messages: Callable[[list[int], bool], dict[str, object]] | None = None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, payload: object, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def get_con(self) -> sqlite3.Connection:
            path = db_path() if callable(db_path) else db_path
            con = sqlite3.connect(path)
            con.row_factory = sqlite3.Row
            return con

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_html(INDEX_HTML)
            elif parsed.path == "/api/search":
                self.handle_search(parse_qs(parsed.query))
            elif parsed.path == "/api/years":
                self.handle_years()
            elif parsed.path == "/api/capabilities":
                self.send_json(capabilities() if capabilities else {"editable": False})
            elif parsed.path == "/api/message":
                self.handle_message(parse_qs(parsed.query))
            else:
                self.send_json({"error": "찾을 수 없는 주소입니다."}, 404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/delete":
                self.send_json({"error": "찾을 수 없는 주소입니다."}, 404)
                return
            if delete_messages is None:
                self.send_json({"error": "이 화면에서는 삭제할 수 없습니다."}, 400)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            try:
                ids = [int(value) for value in payload.get("ids", [])]
                result = delete_messages(ids, bool(payload.get("conversation", True)))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
                return
            self.send_json(result)

        def handle_years(self) -> None:
            with self.get_con() as con:
                rows = con.execute(
                    """
                    select distinct substr(parsed_date, 1, 4) as year
                    from messages
                    where parsed_date is not null and length(parsed_date) >= 4
                    order by year desc
                    """
                ).fetchall()
            years = [row["year"] for row in rows if row["year"] and row["year"].isdigit()]
            self.send_json({"years": years})

        def date_range_for_period(self, period: str) -> tuple[str, str] | None:
            today = date.today()
            if period == "today":
                start = today
                end = today + timedelta(days=1)
            elif period == "last7":
                start = today - timedelta(days=6)
                end = today + timedelta(days=1)
            elif period == "this_month":
                start = today.replace(day=1)
                end = self.add_month(start)
            elif period == "last_month":
                this_month = today.replace(day=1)
                start = self.add_month(this_month, -1)
                end = this_month
            elif period == "this_year":
                start = today.replace(month=1, day=1)
                end = date(today.year + 1, 1, 1)
            else:
                return None
            return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")

        def add_month(self, value: date, months: int = 1) -> date:
            month_index = value.year * 12 + value.month - 1 + months
            year = month_index // 12
            month = month_index % 12 + 1
            return date(year, month, 1)

        def handle_search(self, params: dict[str, list[str]]) -> None:
            query = params.get("q", [""])[0].strip()
            source = params.get("source", [""])[0]
            box = params.get("box", [""])[0]
            period = params.get("period", [""])[0]
            year = params.get("year", [""])[0]
            month = params.get("month", [""])[0]
            limit = min(int(params.get("limit", ["100"])[0]), 300)
            offset = max(int(params.get("offset", ["0"])[0]), 0)
            grouped = params.get("grouped", [""])[0] == "1"
            has_attachment = params.get("has_attachment", [""])[0] == "1"

            where = []
            sql_params: dict[str, object] = {"limit": limit, "offset": offset}
            if query:
                keywords = [keyword for keyword in query.split() if keyword]
                if not keywords:
                    keywords = [query]
                for index, keyword in enumerate(keywords):
                    key = f"query{index}"
                    search_fields = [
                        f"title like :{key}",
                        f"person like :{key}",
                        f"sender like :{key}",
                        f"body_text like :{key}",
                        f"coalesce(attachment_names, '') like :{key}",
                    ]
                    if box == "send":
                        search_fields.append(f"receiver like :{key}")
                    where.append(f"({' or '.join(search_fields)})")
                    sql_params[key] = f"%{keyword}%"
            if source in {"old", "new"}:
                where.append("source_db = :source")
                sql_params["source"] = source
            if box in {"recv", "send"}:
                where.append("box = :box")
                sql_params["box"] = box
            if has_attachment:
                where.append("coalesce(attachment_names, '') <> ''")
            date_range = self.date_range_for_period(period)
            if date_range:
                where.append("parsed_date >= :date_start and parsed_date < :date_end")
                sql_params["date_start"], sql_params["date_end"] = date_range
            elif year and year.isdigit() and len(year) == 4:
                if month and month.isdigit() and 1 <= int(month) <= 12:
                    start_date = date(int(year), int(month), 1)
                    end_date = self.add_month(start_date)
                    where.append("parsed_date >= :date_start and parsed_date < :date_end")
                    sql_params["date_start"] = start_date.strftime("%Y/%m/%d")
                    sql_params["date_end"] = end_date.strftime("%Y/%m/%d")
                else:
                    where.append("parsed_date >= :date_start and parsed_date < :date_end")
                    sql_params["date_start"] = f"{year}/01/01"
                    sql_params["date_end"] = f"{int(year) + 1}/01/01"
            elif month and month.isdigit() and 1 <= int(month) <= 12:
                where.append("substr(parsed_date, 6, 2) = :month")
                sql_params["month"] = month

            where_sql = "where " + " and ".join(where) if where else ""
            with self.get_con() as con:
                rows = con.execute(
                    f"""
                    select
                        id, source_db, source_file, box, original_key, parsed_date, title, person, body_text,
                        case when box = 'recv' then coalesce(is_unread, 0) else 0 end as is_unread,
                        case when body_text like '%님이 보낸글 >>%' then 1 else 0 end as has_quote,
                        case when coalesce(attachment_names, '') <> '' then 1 else 0 end as has_attachment
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
                item["owner_name"] = owner_name_from_source_file(row["source_file"])
                item["snippet"] = shorten(row["body_text"], 180)
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
        if "attachment_names" not in columns:
            con.execute("alter table messages add column attachment_names text")
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
