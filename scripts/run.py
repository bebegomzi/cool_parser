from __future__ import annotations

import argparse
import csv
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


MESSAGE_COLUMNS = [
    "source_db",
    "source_file",
    "box",
    "original_key",
    "date",
    "parsed_date",
    "title",
    "person",
    "sender",
    "receiver",
    "body_text",
    "body_raw",
    "deleted_date",
    "is_unread",
    "recovery_status",
    "body_hash",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="메시지 DB를 준비한 뒤 뷰어를 실행합니다. 기본값은 파싱 후 뷰어 실행입니다."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--use-existing",
        action="store_true",
        help="파싱하지 않고 기존 outputs/merged_messages.sqlite를 바로 엽니다.",
    )
    mode.add_argument(
        "--from-csv",
        type=Path,
        help="이미 파싱된 messages.csv를 임시 SQLite로 바꾼 뒤 뷰어를 엽니다.",
    )
    mode.add_argument(
        "--backup",
        action="store_true",
        help="input 폴더에 넣어둔 .udb 사본들을 파싱한 뒤 뷰어를 엽니다.",
    )
    parser.add_argument(
        "--live-db",
        type=Path,
        default=None,
        help="바로 읽을 CoolMessenger .udb 경로입니다. 기본값은 LOCALAPPDATA의 정현민.udb입니다.",
    )
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="새로 파싱할 결과를 저장할 작업 폴더입니다. 기본값은 outputs/run_타임스탬프입니다.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="뷰어 종료 후 새로 만든 작업 폴더를 지우지 않고 남깁니다.",
    )
    parser.add_argument("--db", type=Path, default=None, help="--use-existing에서 열 SQLite 경로")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    return parser.parse_args()


def default_live_db() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise SystemExit("LOCALAPPDATA 환경 변수를 찾지 못했습니다. --live-db로 경로를 지정하세요.")
    return Path(local_app_data) / "CoolMessenger" / "Memo." / "정현민.udb"


def backup_sources(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise SystemExit(f"input 폴더가 없습니다: {input_dir}")
    paths = sorted(input_dir.glob("*.udb"))
    if not paths:
        raise SystemExit(f"input 폴더에 .udb 파일이 없습니다: {input_dir}")
    return paths


def run_command(args: list[str]) -> None:
    subprocess.run(args, check=True)


def copy_live_db_to_temp(live_db: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp_dir = tempfile.TemporaryDirectory(prefix="cool_parser_")
    copied_path = Path(temp_dir.name) / live_db.name
    shutil.copy2(live_db, copied_path)
    return temp_dir, copied_path


def init_csv_db(path: Path) -> sqlite3.Connection:
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
            deleted_date text,
            is_unread integer not null default 0,
            recovery_status text not null,
            body_hash text
        )
        """
    )
    con.execute("create index idx_messages_date on messages(parsed_date, date)")
    return con


def csv_to_sqlite(csv_path: Path, db_path: Path) -> Path:
    if not csv_path.exists():
        raise SystemExit(f"CSV 파일이 없습니다: {csv_path}")

    con = init_csv_db(db_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = {column: row.get(column, "") for column in MESSAGE_COLUMNS}
            if not values["source_file"]:
                values["source_file"] = csv_path.name
            if not values["body_raw"]:
                values["body_raw"] = ""
            if not values["body_hash"]:
                values["body_hash"] = ""
            con.execute(
                f"""
                insert into messages ({", ".join(MESSAGE_COLUMNS)})
                values ({", ".join("?" for _ in MESSAGE_COLUMNS)})
                """,
                [values[column] for column in MESSAGE_COLUMNS],
            )
    con.commit()
    con.close()
    return db_path


def viewer_args(db_path: Path, host: str, port: int, should_open: bool) -> list[str]:
    args = [
        sys.executable,
        "scripts/viewer.py",
        "--db",
        str(db_path),
        "--host",
        host,
        "--port",
        str(port),
    ]
    if should_open:
        args.append("--open")
    return args


def make_work_dir(output_dir: Path, explicit_work_dir: Path | None) -> Path:
    if explicit_work_dir is not None:
        return explicit_work_dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"run_{stamp}"


def main() -> None:
    args = parse_args()
    output_db = args.output_dir / "merged_messages.sqlite"
    work_dir = make_work_dir(args.output_dir, args.work_dir)
    temp_live_dir: tempfile.TemporaryDirectory[str] | None = None
    cleanup_work_dir = False

    try:
        if args.from_csv:
            db_path = csv_to_sqlite(args.from_csv, args.output_dir / "view_from_csv.sqlite")
        elif args.use_existing:
            db_path = args.db or output_db
            if not db_path.exists():
                raise SystemExit(f"SQLite 파일이 없습니다: {db_path}")
        else:
            merge_args = [
                sys.executable,
                "scripts/merge_messages.py",
                "--output-dir",
                str(work_dir),
            ]
            if args.backup:
                for path in backup_sources(args.input_dir):
                    merge_args.extend(["--db", f"{path.stem}={path}"])
            else:
                live_db = args.live_db or default_live_db()
                if not live_db.exists():
                    raise SystemExit(f"라이브 DB 파일이 없습니다: {live_db}")
                temp_live_dir, copied_live_db = copy_live_db_to_temp(live_db)
                merge_args.extend(["--db", f"live={copied_live_db}"])

            run_command(merge_args)
            db_path = work_dir / "merged_messages.sqlite"
            cleanup_work_dir = not args.keep_work_dir

        run_command(viewer_args(db_path, args.host, args.port, not args.no_open))
    finally:
        if temp_live_dir is not None:
            temp_live_dir.cleanup()
        if cleanup_work_dir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
