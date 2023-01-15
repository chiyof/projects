#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# copyright (c) K.Fujii 2021,2022
# created : Mar 7, 2021
# last modified: Dec 25, 2022
"""
publist.py:
指定されたディレクトリ以下にあるファイルの情報を収集してDBに登録する
対象ディレクトリは publist.json にて指定する
"""

import argparse
import sqlite3
import json
import logging
import time
import datetime
from os import environ, walk
from pathlib import Path
from tqdm import tqdm


logger = logging.getLogger(__name__)


def lsr_files(directory):
    """List all the files under specified directory

    Args:
        directory (str): one directory to list all files under it.

    Returns:
        ret (list): list of Path objects under the specified directory.
    """
    path = Path(directory)
    ret = list(path.glob("**/*"))
    return ret


def cleanup(con: sqlite3.Connection, cur: sqlite3.Cursor):
    """DBのデータが示すファイルが存在するかどうかを確認し、存在しなければDBからレコードを削除する

    Args:
        con (sqlite3.Connection): _description_
        cur (sqlite3.Cursor): _description_

    """
    SQL = "SELECT * FROM filelist"

    # res = cur.execute(SQL) とすると、forループが最初のexecute()で終わる
    # おそらく res が壊れるので、横着せずにfetchall()すること。
    cur.execute(SQL)
    res = cur.fetchall()
    with tqdm(res) as pbar:
        for r in pbar:
            p = Path(r["directory"], r["filename"])
            if p.exists():
                continue
            else:
                logger.debug(f"clean-up {p}")
                SQL = f"""
                    delete from filelist
                    where directory="{r['directory']}"
                    and filename="{r['filename']}"
                """
                cur.execute(SQL)
                con.commit()


def count_files(p: Path):
    logger.info("count files")
    count = 0
    # python 3.12 supports Path.walk() but 3.11 doesn't.
    for root, dirs, files in walk(str(p), onerror=print):
        count += len(files)
    logger.info(f"total files: {count}")
    return count


def index_files(p: Path, con: sqlite3.Connection, cur: sqlite3.Cursor):
    """Get video info from the video file using OpenCV"""
    file_count = count_files(p)
    if p.is_file():
        target = [p]
    else:
        target = p.glob("**/*")
    with tqdm(target, leave=True, total=file_count * 1.15) as pbar:
        for f in pbar:
            if f.is_dir():
                logger.debug(f)
                con.commit()
                continue
            f = f.absolute()
            # dirname = str(f.parent).replace("'", "''")
            dirname = str(f.parent)
            # fname = f.name.replace("'", "''")
            fname = f.name
            timestamp = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)
            )
            if fname == "ls-R":
                continue
            else:
                logger.debug(f)
                # 処理時間短縮のためデータベースにすでにあるかどうかを確認する
                cur.execute(
                    f"""
                    SELECT * FROM filelist WHERE filename="{fname}"
                        AND directory="{dirname}" AND datetime="{timestamp}"
                    """
                )
                data = cur.fetchall()
                try:
                    r = [dict(d) for d in data]
                except ValueError:
                    r = []
                # データがあれば登録不要
                if r:
                    logger.debug(f"already registered, skip {fname}")
                    continue

                # その他に .keyframe, .err がある
                logger.debug(f"updating {fname}")
                SQL = f"""INSERT INTO filelist VALUES ("{fname}", "{dirname}", {f.stat().st_size}, "{timestamp}")
                    ON CONFLICT (directory, filename)
                    DO UPDATE SET datetime = "{timestamp}", filesize = {f.stat().st_size}
                    """

                try:
                    cur.execute(SQL)
                except sqlite3.OperationalError as e:
                    print(e)
                    logger.error(SQL)
                    exit(-1)
                except sqlite3.ProgrammingError as e:
                    print(e)
                    logger.error(SQL)
                    exit(-1)
                else:
                    logger.debug(f"inserted {dirname}/{fname}")


def create_table(cur):
    # talbe filelist
    # ----------------------
    # filename    | TEXT
    # directory   | TEXT
    # filesize    | INTEGER
    # datetime    | TEXT
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS filelist (
                filename TEXT NOT NULL,
                directory TEXT NOT NULL,
                filesize INTEGER NOT NULL DEFAULT 0,
                datetime TEXT DEFAULT "",
                PRIMARY KEY (directory, filename))
            """
        )
    except sqlite3.OperationalError:
        # すでにTABLEがある
        pass
    return


def main():
    # read target directories from json file.
    config = Path(environ["XDG_CONFIG_HOME"]) / "publist.json"
    db_name = Path("publist.db")
    db_dir = Path(environ["XDG_DATA_HOME"]) / "publist"
    db_path = db_dir / db_name
    # log_dir は $XDG_STATE_HOME が Ver.0.8から標準になった
    # $XDG_STATE_HOME がない場合は ~/.local/state が使われる
    log_dir = db_dir / "log"
    log_name = Path(time.strftime("publist-%Y-%m-%d.log"))
    target_dirs = []
    try:
        with open(config, encoding="utf-8") as f:
            json_obj = json.load(f)
    except FileNotFoundError:
        target_dirs = [Path.cwd()]
        db_path = Path("./index-db.db")
        log_path = Path("./publist.log")
    else:
        try:
            target_dirs = json_obj["target_dirs"]
        except IndexError:
            target_dirs = [Path.cwd()]
        try:
            db_name = Path(json_obj["index_db"])
        except IndexError:
            pass
        try:
            db_path = Path(json_obj["db_dir"]) / db_name
        except IndexError:
            db_path = db_dir / db_name
        try:
            log_path = Path(json_obj["log_dir"]) / log_name
        except IndexError:
            log_path = log_dir / log_name

    parser = argparse.ArgumentParser(
        description="pubディレクトリ以下にあるファイルのインデックスデータベースを生成する",
        #    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f"指定がない場合のデフォルトターゲット: {target_dirs}",
    )
    parser.add_argument(
        "directories",
        metavar="dir",
        type=Path,
        nargs="*",
        default=target_dirs,
        help="directories for search video files",
    )
    parser.add_argument(
        "-c",
        "--cleanup",
        action="store_const",
        const=True,
        default=False,
        help="Clean up database",
    )
    parser.add_argument("-D", "--DB", type=Path, help="specify database")
    parser.add_argument(
        "-d",
        "--debug",
        metavar="debug",
        action="store_const",
        const=True,
        default=False,
        help="Print Debug information",
    )
    args = parser.parse_args()

    # add log file handler to logger
    fh = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.DB:
        logger.info(f"DB file: {args.DB}")
        db_path = args.db

    logger.debug(target_dirs)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    create_table(cur)

    dirs = args.directories
    time_start = time.perf_counter()
    st = datetime.datetime.now()

    if args.cleanup:
        cleanup(conn, cur)
    else:
        for d in dirs:
            p = Path(d)
            if not p.exists():
                logger.info("%s is not exist", p)
            else:
                index_files(p, conn, cur)

    time_end = time.perf_counter()
    time_diff = time_end - time_start
    time_ellaps = time.gmtime(time_diff)
    logger.info(
        "start at : %02d:%02d:%02d.%04d",
        st.hour,
        st.minute,
        st.second,
        st.microsecond,
    )
    logger.info(
        "process time : %02d:%02d:%02d.%04d",
        time_ellaps.tm_hour,
        time_ellaps.tm_min,
        time_ellaps.tm_sec,
        (time_diff - int(time_diff)) * 1000,
    )
    conn.close()


if __name__ == "__main__":
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    main()
