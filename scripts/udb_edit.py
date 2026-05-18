from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


TABLES = {
    "recv": "tbl_recv",
    "send": "tbl_send",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="실험용 .udb 사본 편집 도구")
    parser.add_argument("--target", type=Path, required=True, help="수정할 .udb 사본")
    parser.add_argument("--backup-dir", type=Path, default=Path("lab/backups"))
    parser.add_argument("--log", type=Path, default=Path("lab/edit_log.jsonl"))
    parser.add_argument("--dry-run", action="store_true", help="변경하지 않고 계획만 출력")

    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update-message", help="메시지 제목/본문을 수정합니다.")
    update.add_argument("--box", choices=TABLES.keys(), required=True)
    update.add_argument("--key", type=int, required=True)
    update.add_argument("--title")
    update.add_argument("--body")

    import_msg = sub.add_parser("import-message", help="다른 .udb에서 메시지 1건을 새 행으로 가져옵니다.")
    import_msg.add_argument("--source", type=Path, required=True)
    import_msg.add_argument("--box", choices=TABLES.keys(), required=True)
    import_msg.add_argument("--key", type=int, required=True)

    delete = sub.add_parser("delete-message", help="메시지 1건을 물리 삭제합니다.")
    delete.add_argument("--box", choices=TABLES.keys(), required=True)
    delete.add_argument("--key", type=int, required=True)

    return parser.parse_args()


def connect(path: Path, *, readonly: bool) -> sqlite3.Connection:
    if readonly:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    else:
        con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def make_backup(path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def append_log(log_path: Path, payload: dict[str, object]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": datetime.now().isoformat(timespec="seconds"), **payload}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f"pragma table_info({table})")]


def integrity_check(con: sqlite3.Connection) -> str:
    return str(con.execute("pragma integrity_check").fetchone()[0])


def update_message(args: argparse.Namespace, backup_path: Path | None) -> None:
    table = TABLES[args.box]
    updates = []
    values = []
    if args.title is not None:
        updates.append("Title = ?")
        values.append(args.title)
    if args.body is not None:
        updates.append("MessageText = ?")
        values.append(args.body)
    if not updates:
        raise SystemExit("수정할 --title 또는 --body를 지정하세요.")

    con = connect(args.target, readonly=False)
    try:
        before = con.execute(
            f"select MessageKey, Title, MessageText from {table} where MessageKey = ?",
            (args.key,),
        ).fetchone()
        if before is None:
            raise SystemExit(f"메시지를 찾지 못했습니다: {args.box} {args.key}")
        if args.dry_run:
            print(dict(before))
            return
        con.execute("begin immediate")
        con.execute(
            f"update {table} set {', '.join(updates)} where MessageKey = ?",
            (*values, args.key),
        )
        con.commit()
        check = integrity_check(con)
    finally:
        con.close()

    append_log(
        args.log,
        {
            "command": "update-message",
            "target": str(args.target),
            "backup": str(backup_path) if backup_path else "",
            "box": args.box,
            "key": args.key,
            "changed_fields": [field.split()[0] for field in updates],
            "integrity_check": check,
        },
    )
    print(f"updated {args.box}:{args.key}")
    print(f"integrity_check={check}")


def import_message(args: argparse.Namespace, backup_path: Path | None) -> None:
    table = TABLES[args.box]
    source_con = connect(args.source, readonly=True)
    target_con = connect(args.target, readonly=False)
    try:
        source_row = source_con.execute(
            f"select * from {table} where MessageKey = ?",
            (args.key,),
        ).fetchone()
        if source_row is None:
            raise SystemExit(f"원본 메시지를 찾지 못했습니다: {args.box} {args.key}")

        target_cols = table_columns(target_con, table)
        insert_cols = [col for col in target_cols if col != "MessageKey"]
        values = [source_row[col] for col in insert_cols]

        if args.dry_run:
            print({col: source_row[col] for col in ["MessageKey", "Title", "MessageText"] if col in source_row.keys()})
            return

        target_con.execute("begin immediate")
        target_con.execute(
            f"insert into {table} ({', '.join(insert_cols)}) values ({', '.join('?' for _ in insert_cols)})",
            values,
        )
        new_key = int(target_con.execute("select last_insert_rowid()").fetchone()[0])
        target_con.commit()
        check = integrity_check(target_con)
    finally:
        source_con.close()
        target_con.close()

    append_log(
        args.log,
        {
            "command": "import-message",
            "source": str(args.source),
            "target": str(args.target),
            "backup": str(backup_path) if backup_path else "",
            "box": args.box,
            "source_key": args.key,
            "new_key": new_key,
            "integrity_check": check,
        },
    )
    print(f"imported {args.box}:{args.key} -> {new_key}")
    print(f"integrity_check={check}")


def delete_message(args: argparse.Namespace, backup_path: Path | None) -> None:
    table = TABLES[args.box]
    con = connect(args.target, readonly=False)
    try:
        before = con.execute(
            f"select MessageKey, Title, MessageText from {table} where MessageKey = ?",
            (args.key,),
        ).fetchone()
        if before is None:
            raise SystemExit(f"메시지를 찾지 못했습니다: {args.box} {args.key}")
        if args.dry_run:
            print(dict(before))
            return

        con.execute("begin immediate")
        con.execute(f"delete from {table} where MessageKey = ?", (args.key,))
        con.commit()
        check = integrity_check(con)
    finally:
        con.close()

    append_log(
        args.log,
        {
            "command": "delete-message",
            "target": str(args.target),
            "backup": str(backup_path) if backup_path else "",
            "box": args.box,
            "key": args.key,
            "integrity_check": check,
        },
    )
    print(f"deleted {args.box}:{args.key}")
    print(f"integrity_check={check}")


def main() -> None:
    args = parse_args()
    if not args.target.exists():
        raise SystemExit(f"대상 DB가 없습니다: {args.target}")

    backup_path = None
    if not args.dry_run:
        backup_path = make_backup(args.target, args.backup_dir)
        print(f"backup={backup_path}")

    if args.command == "update-message":
        update_message(args, backup_path)
    elif args.command == "import-message":
        import_message(args, backup_path)
    elif args.command == "delete-message":
        delete_message(args, backup_path)


if __name__ == "__main__":
    main()
