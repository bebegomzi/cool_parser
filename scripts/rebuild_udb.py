from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


TABLE_ORDER = [
    "tbl_dbInfo",
    "tbl_member",
    "tbl_alarm",
    "tbl_autotext",
    "tbl_recv",
    "tbl_send",
]

ROW_BY_KEY_TABLES = {
    "tbl_recv": "MessageKey",
    "tbl_send": "MessageKey",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="손상된 .udb를 읽히는 행만 새 .udb로 재구성합니다.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("lab/rebuild_failed_rows.csv"))
    return parser.parse_args()


def connect_readonly(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def connect_output(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def sqlite_master_rows(con: sqlite3.Connection, object_type: str) -> list[sqlite3.Row]:
    return con.execute(
        """
        select type, name, tbl_name, sql
        from sqlite_master
        where type = ?
          and sql is not null
          and name not like 'sqlite_%'
        order by name
        """,
        (object_type,),
    ).fetchall()


def create_schema(source: sqlite3.Connection, output: sqlite3.Connection) -> None:
    table_sql = {row["name"]: row["sql"] for row in sqlite_master_rows(source, "table")}
    for table in TABLE_ORDER:
        if table in table_sql:
            output.execute(table_sql[table])
    for row in sqlite_master_rows(source, "index"):
        output.execute(row["sql"])
    output.commit()


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f"pragma table_info({table})")]


def insert_row(output: sqlite3.Connection, table: str, columns: list[str], row: sqlite3.Row) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    output.execute(
        f"insert into {table} ({column_sql}) values ({placeholders})",
        [row[column] for column in columns],
    )


def copy_table_direct(source: sqlite3.Connection, output: sqlite3.Connection, table: str) -> tuple[int, int]:
    columns = table_columns(source, table)
    copied = 0
    failed = 0
    try:
        rows = source.execute(f"select * from {table}")
        for row in rows:
            insert_row(output, table, columns, row)
            copied += 1
    except Exception:
        failed += 1
    return copied, failed


def key_range(source: sqlite3.Connection, table: str, key_column: str) -> tuple[int, int]:
    row = source.execute(f"select min({key_column}), max({key_column}) from {table}").fetchone()
    if row[0] is None or row[1] is None:
        return 0, -1
    return int(row[0]), int(row[1])


def copy_table_by_key(
    source: sqlite3.Connection,
    output: sqlite3.Connection,
    table: str,
    key_column: str,
) -> tuple[int, list[tuple[str, int, str]]]:
    columns = table_columns(source, table)
    copied = 0
    failures: list[tuple[str, int, str]] = []
    start, end = key_range(source, table, key_column)

    for key in range(start, end + 1):
        try:
            row = source.execute(f"select * from {table} where {key_column} = ?", (key,)).fetchone()
            if row is None:
                continue
            insert_row(output, table, columns, row)
            copied += 1
        except Exception as exc:
            failures.append((table, key, repr(exc)))
    return copied, failures


def sync_sqlite_sequence(source: sqlite3.Connection, output: sqlite3.Connection) -> None:
    exists = output.execute(
        "select count(*) from sqlite_master where type='table' and name='sqlite_sequence'"
    ).fetchone()[0]
    if not exists:
        return
    try:
        output.execute("delete from sqlite_sequence")
        for row in source.execute("select name, seq from sqlite_sequence"):
            output.execute("insert into sqlite_sequence(name, seq) values (?, ?)", (row["name"], row["seq"]))
    except Exception:
        for table, key_column in ROW_BY_KEY_TABLES.items():
            seq = output.execute(f"select coalesce(max({key_column}), 0) from {table}").fetchone()[0]
            output.execute(
                "insert or replace into sqlite_sequence(name, seq) values (?, ?)",
                (table, seq),
            )


def write_failure_report(path: Path, failures: list[tuple[str, int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["table", "key", "error"])
        writer.writerows(failures)


def rebuild(source_path: Path, output_path: Path, report_path: Path) -> None:
    source = connect_readonly(source_path)
    output = connect_output(output_path)
    failures: list[tuple[str, int, str]] = []
    summaries = []
    try:
        create_schema(source, output)
        for table in TABLE_ORDER:
            if table in ROW_BY_KEY_TABLES:
                copied, table_failures = copy_table_by_key(source, output, table, ROW_BY_KEY_TABLES[table])
                failures.extend(table_failures)
                summaries.append((table, copied, len(table_failures)))
            else:
                copied, failed = copy_table_direct(source, output, table)
                summaries.append((table, copied, failed))
        sync_sqlite_sequence(source, output)
        output.commit()
        integrity = output.execute("pragma integrity_check").fetchone()[0]
    finally:
        source.close()
        output.close()

    write_failure_report(report_path, failures)
    print(f"output={output_path}")
    print(f"report={report_path}")
    print(f"integrity_check={integrity}")
    for table, copied, failed in summaries:
        print(f"{table}: copied={copied}, failed={failed}")


def main() -> None:
    args = parse_args()
    rebuild(args.source, args.output, args.report)


if __name__ == "__main__":
    main()
