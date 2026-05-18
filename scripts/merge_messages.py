from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
from pathlib import Path


RECV_COLUMNS = {
    "key": "MessageKey",
    "date": "ReceiveDate",
    "title": "Title",
    "person": "Sender",
    "sender": "Sender",
    "receiver": "ReferenceList",
    "body_text": "MessageText",
    "body_raw": "MessageBody",
    "deleted_date": "DeletedDate",
    "is_unread": "IsUnRead",
    "file_path": "FilePath",
    "link_url": "LinkURL",
}

SEND_COLUMNS = {
    "key": "MessageKey",
    "date": "SendDate",
    "title": "Title",
    "person": "Receiver",
    "sender": "",
    "receiver": "Receiver",
    "body_text": "MessageText",
    "body_raw": "MessageBody",
    "deleted_date": "DeletedDate",
    "is_unread": "",
    "file_path": "FilePath",
    "link_url": "LinkURL",
}

DATE_RE = re.compile(r"^(\d{4}/\d{2}/\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="손상/정상 .udb 메시지 DB를 읽어 통합 SQLite 아카이브를 만듭니다."
    )
    parser.add_argument(
        "--db",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="읽을 .udb 파일입니다. 예: --db live=C:\\path\\user.udb",
    )
    parser.add_argument("--old-db", type=Path, default=None)
    parser.add_argument("--new-db", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    return parser.parse_args()


def parse_source_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        path = Path(value)
        return path.stem, path
    label, raw_path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise SystemExit(f"DB 라벨이 비어 있습니다: {value}")
    return label, Path(raw_path)


def collect_sources(args: argparse.Namespace) -> list[tuple[str, Path]]:
    sources = [parse_source_spec(value) for value in args.db]
    if args.old_db is not None:
        sources.append(("old", args.old_db))
    if args.new_db is not None:
        sources.append(("new", args.new_db))
    if not sources:
        source_dir = Path("sources")
        if source_dir.exists():
            sources.extend((path.stem, path) for path in sorted(source_dir.glob("*.udb")))
    if not sources:
        raise SystemExit("읽을 .udb 파일이 없습니다. --db LABEL=PATH를 지정하세요.")
    return sources


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def init_output_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    con = sqlite3.connect(path)
    con.execute(
        """
        create table messages (
            id integer primary key autoincrement,
            source_db text not null,
            source_file text not null,
            box text not null,
            original_key integer not null,
            date text,
            parsed_date text,
            title text,
            person text,
            sender text,
            receiver text,
            body_text text,
            body_raw text,
            attachment_names text,
            deleted_date text,
            is_unread integer not null default 0,
            recovery_status text not null,
            body_hash text
        )
        """
    )
    con.execute(
        """
        create table failed_message_keys (
            id integer primary key autoincrement,
            source_db text not null,
            source_file text not null,
            box text not null,
            original_key integer not null,
            error text not null
        )
        """
    )
    con.execute(
        "create index idx_messages_date on messages(parsed_date, date)"
    )
    con.execute(
        "create index idx_messages_lookup on messages(source_db, box, original_key)"
    )
    con.execute(
        "create index idx_messages_body_hash on messages(body_hash)"
    )
    return con


def get_key_range(con: sqlite3.Connection, table: str) -> tuple[int, int]:
    row = con.execute(f"select min(MessageKey), max(MessageKey) from {table}").fetchone()
    if row[0] is None or row[1] is None:
        return 0, -1
    return int(row[0]), int(row[1])


def normalize_date(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    match = DATE_RE.match(text)
    return match.group(1) if match else text


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def text_hash(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_value(row: sqlite3.Row, column: str) -> str:
    if not column:
        return ""
    return clean_text(row[column])


def load_member_names(con: sqlite3.Connection) -> dict[str, str]:
    names = {}
    try:
        rows = con.execute("select K_MemberID, MemberID, MemberName from tbl_member")
    except Exception:
        return names

    for row in rows:
        key = str(row["K_MemberID"])
        name = clean_text(row["MemberName"]) or clean_text(row["MemberID"])
        if name:
            names[key] = name
    return names


def resolve_member_list(value: str, member_names: dict[str, str]) -> str:
    if not value:
        return ""
    if not value.startswith("|"):
        return value

    ids = [item for item in value.split("|") if item]
    if len(ids) > 1:
        ids = ids[1:]
    names = [member_names.get(item, f"알 수 없음({item})") for item in ids]
    return "; ".join(names)


def parse_attachment_names(file_path: str, link_url: str) -> str:
    names = []
    parts = file_path.split("|") if file_path else []
    if len(parts) >= 5:
        for index in range(4, len(parts), 3):
            name = clean_text(parts[index])
            if name:
                names.append(name.rstrip("\\/"))

    link_url = clean_text(link_url)
    if link_url:
        names.append(link_url)

    return "; ".join(dict.fromkeys(names))


def recover_table(
    source_con: sqlite3.Connection,
    output_con: sqlite3.Connection,
    *,
    source_db: str,
    source_file: str,
    table: str,
    box: str,
    columns: dict[str, str],
    member_names: dict[str, str],
) -> tuple[int, int]:
    min_key, max_key = get_key_range(source_con, table)
    recovered = 0
    failed = 0

    sql = f"select * from {table} where MessageKey = ?"
    for key in range(min_key, max_key + 1):
        try:
            row = source_con.execute(sql, (key,)).fetchone()
            if row is None:
                continue

            body_text = get_value(row, columns["body_text"])
            receiver = get_value(row, columns["receiver"])
            if box == "recv":
                receiver = resolve_member_list(receiver, member_names)
            attachment_names = parse_attachment_names(
                get_value(row, columns["file_path"]),
                get_value(row, columns["link_url"]),
            )
            output_con.execute(
                """
                insert into messages (
                    source_db, source_file, box, original_key, date, parsed_date,
                    title, person, sender, receiver, body_text, body_raw,
                    attachment_names, deleted_date, is_unread, recovery_status, body_hash
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_db,
                    source_file,
                    box,
                    int(row[columns["key"]]),
                    get_value(row, columns["date"]),
                    normalize_date(row[columns["date"]]),
                    get_value(row, columns["title"]),
                    get_value(row, columns["person"]),
                    get_value(row, columns["sender"]),
                    receiver,
                    body_text,
                    get_value(row, columns["body_raw"]),
                    attachment_names,
                    get_value(row, columns["deleted_date"]),
                    int(get_value(row, columns["is_unread"]) or 0),
                    "ok",
                    text_hash(body_text),
                ),
            )
            recovered += 1
        except Exception as exc:
            output_con.execute(
                """
                insert into failed_message_keys (
                    source_db, source_file, box, original_key, error
                )
                values (?, ?, ?, ?, ?)
                """,
                (source_db, source_file, box, key, repr(exc)),
            )
            failed += 1

    return recovered, failed


def write_csv(con: sqlite3.Connection, path: Path, query: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cur = con.execute(query)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([description[0] for description in cur.description])
        writer.writerows(cur)


def write_reports(con: sqlite3.Connection, output_dir: Path) -> None:
    write_csv(
        con,
        output_dir / "failed_message_keys.csv",
        """
        select source_db, source_file, box, original_key, error
        from failed_message_keys
        order by source_db, box, original_key
        """,
    )
    write_csv(
        con,
        output_dir / "duplicate_candidates.csv",
        """
        select
            body_hash,
            count(*) as candidate_count,
            group_concat(source_db || ':' || box || ':' || original_key, ' | ') as message_refs,
            min(parsed_date) as first_date,
            max(parsed_date) as last_date,
            min(title) as sample_title,
            min(person) as sample_person
        from messages
        where body_hash <> ''
        group by body_hash
        having count(*) > 1
        order by candidate_count desc, first_date
        """,
    )
    write_csv(
        con,
        output_dir / "messages.csv",
        """
        select
            source_db, box, original_key, parsed_date, date, title, person,
            sender, receiver, body_text, attachment_names, deleted_date, is_unread, recovery_status
        from messages
        order by parsed_date, source_db, box, original_key
        """,
    )


def merge_sources(sources: list[tuple[str, Path]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_db = output_dir / "merged_messages.sqlite"
    output_con = init_output_db(output_db)
    summaries = []

    for source_db, path in sources:
        if not path.exists():
            raise SystemExit(f"DB 파일이 없습니다: {path}")
        source_con = connect_readonly(path)
        try:
            member_names = load_member_names(source_con)
            for table, box, columns in [
                ("tbl_recv", "recv", RECV_COLUMNS),
                ("tbl_send", "send", SEND_COLUMNS),
            ]:
                recovered, failed = recover_table(
                    source_con,
                    output_con,
                    source_db=source_db,
                    source_file=path.name,
                    table=table,
                    box=box,
                    columns=columns,
                    member_names=member_names,
                )
                output_con.commit()
                summaries.append((source_db, box, recovered, failed))
        finally:
            source_con.close()

    write_reports(output_con, output_dir)
    output_con.commit()

    total = output_con.execute("select count(*) from messages").fetchone()[0]
    failed_total = output_con.execute("select count(*) from failed_message_keys").fetchone()[0]
    duplicate_groups = output_con.execute(
        """
        select count(*) from (
            select body_hash
            from messages
            where body_hash <> ''
            group by body_hash
            having count(*) > 1
        )
        """
    ).fetchone()[0]
    output_con.close()

    print(f"output_db={output_db}")
    print(f"messages={total}")
    print(f"failed_keys={failed_total}")
    print(f"duplicate_candidate_groups={duplicate_groups}")
    for source_db, box, recovered, failed in summaries:
        print(f"{source_db}:{box}: recovered={recovered}, failed={failed}")
    return output_db


def main() -> None:
    args = parse_args()
    merge_sources(collect_sources(args), args.output_dir)


if __name__ == "__main__":
    main()
