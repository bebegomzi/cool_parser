from __future__ import annotations

import argparse
import sqlite3
import textwrap
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="merged_messages.sqlite에서 메시지를 검색하거나 자세히 봅니다."
    )
    parser.add_argument("query", nargs="?", help="제목, 사람, 본문에서 찾을 검색어")
    parser.add_argument("--db", type=Path, default=Path("outputs/merged_messages.sqlite"))
    parser.add_argument("--limit", type=int, default=20, help="검색 결과 최대 개수")
    parser.add_argument("--source", choices=["old", "new"], help="예전/새 DB 중 하나만 보기")
    parser.add_argument("--box", choices=["recv", "send"], help="받은/보낸 메시지 중 하나만 보기")
    parser.add_argument("--id", type=int, help="검색 대신 특정 통합 메시지 ID를 자세히 보기")
    return parser.parse_args()


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def short(text: object, width: int = 80) -> str:
    if text is None:
        return ""
    cleaned = " ".join(str(text).split())
    return textwrap.shorten(cleaned, width=width, placeholder="...")


def box_label(value: str) -> str:
    return {"recv": "받음", "send": "보냄"}.get(value, value)


def print_row(row: sqlite3.Row) -> None:
    print(
        f"[{row['id']}] {row['parsed_date']} | {row['source_db']} | "
        f"{box_label(row['box'])} | {short(row['person'], 24)}"
    )
    print(f"제목: {short(row['title'], 100)}")
    print(f"본문: {short(row['body_text'], 140)}")
    print()


def search(con: sqlite3.Connection, args: argparse.Namespace) -> None:
    if not args.query:
        raise SystemExit("검색어를 입력하거나 --id를 사용하세요.")

    where = [
        "(title like :query or person like :query or sender like :query or "
        "receiver like :query or body_text like :query)"
    ]
    params: dict[str, object] = {
        "query": f"%{args.query}%",
        "limit": args.limit,
    }

    if args.source:
        where.append("source_db = :source")
        params["source"] = args.source
    if args.box:
        where.append("box = :box")
        params["box"] = args.box

    sql = f"""
        select id, source_db, box, original_key, parsed_date, title, person, body_text
        from messages
        where {" and ".join(where)}
        order by parsed_date, id
        limit :limit
    """
    rows = con.execute(sql, params).fetchall()

    print(f"검색어: {args.query}")
    print(f"표시 결과: {len(rows)}건")
    print()
    for row in rows:
        print_row(row)


def show_detail(con: sqlite3.Connection, message_id: int) -> None:
    row = con.execute(
        """
        select *
        from messages
        where id = ?
        """,
        (message_id,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"ID {message_id} 메시지를 찾지 못했습니다.")

    print(f"통합 ID: {row['id']}")
    print(f"원본: {row['source_db']} / {row['source_file']}")
    print(f"보관함: {box_label(row['box'])}")
    print(f"원래 MessageKey: {row['original_key']}")
    print(f"날짜: {row['date']}")
    print(f"상대방: {row['person']}")
    print(f"보낸 사람: {row['sender']}")
    print(f"받은 사람: {row['receiver']}")
    print(f"제목: {row['title']}")
    print()
    print(row["body_text"] or "")


def main() -> None:
    args = parse_args()
    con = connect(args.db)
    try:
        if args.id is not None:
            show_detail(con, args.id)
        else:
            search(con, args)
    finally:
        con.close()


if __name__ == "__main__":
    main()
