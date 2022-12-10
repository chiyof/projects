#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# copyright (c) K.Fujii 2021,2022
# created : Mar 7, 2021
# last modified: Aug 21, 2022
"""
mp4lsr.py:
MP4ファイルの ls-R ファイルを生成する
対象ディレクトリは targets に列記しておく
MP4ファイルでは末尾にフレームサイズを追加する

音声多重（含む二ヶ国語）の場合には、
"decode_pce: Input buffer exhausted before END element found"
というエラーがopencvから出力されるが、出力の抑制は出来ない模様
"""

import argparse
import sqlite3
import json
import math
import logging
import time
import datetime
from os import environ
from pathlib import Path

import cv2
from natsort import os_sorted


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


def get_video_info(fname: Path):
    """Get frame size data from the video file using OpenCV"""
    video_track = cv2.VideoCapture(str(fname))
    width = video_track.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = video_track.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = video_track.get(cv2.CAP_PROP_FPS)
    fc = video_track.get(cv2.CAP_PROP_FRAME_COUNT)
    try:
        length = fc / fps
    except ZeroDivisionError:
        logger.info("wrong FPS value: %s", fname)
        length = 0
    if length <= 0:
        logger.warn(f"invalid length: {fc} / {fps} on {fname}")
        length = 0
    if width == 0 or height == 0:
        logger.warn(f"invalid frame size: width {width} height {height} on {fname}")

    return int(width), int(height), int(length)


def index_files(p: Path, con: sqlite3.Connection, cur: sqlite3.Cursor):
    """Get video info from the video file using OpenCV"""
    if p.is_file():
        target = [p]
    else:
        target = p.glob("**/*")
    for f in target:
        if f.is_dir():
            logger.info(f)
            con.commit()
            continue
        f = f.resolve()
        filetype = f.suffix.upper()[1:]
        if f.suffix.lower() in [".mp4", ".m2ts", ".m2t", ".mpg", ".ts"]:
            # "mp4" or "m2ts" or "mpg"
            logger.debug(f)
            width, height, length = get_video_info(f)
            if length != 0:
                play_length = time.strftime("%H:%M:%S", time.gmtime(math.ceil(length)))
            else:
                play_length = 0
            timestamp = time.strftime(
                "%Y/%m/%d %H:%M:%S", time.localtime(f.stat().st_mtime)
            )
            cur.execute(
                f'INSERT INTO videolist VALUES ("{f.name}", "{f.parent}", "{filetype}", '
                f'{height}, {width}, "{play_length}", {f.stat().st_size}, "{timestamp}") '
                "on conflict (directory, filename) do nothing"
            )
        else:
            timestamp = time.strftime(
                "%Y/%m/%d %H:%M:%S", time.localtime(f.stat().st_mtime)
            )
            cur.execute(
                f'INSERT INTO videolist VALUES ("{f.name}", "{f.parent}", "{filetype}", '
                f'0, 0, "", {f.stat().st_size}, "{timestamp}") '
                "on conflict (directory, filename) do nothing"
            )


def create_table(cur):
    # talbe videolist
    # ---------------------
    # filename | TEXT
    # dir      | TEXT
    # height   | INTEGER
    # width    | INTEGER
    # len      | TEXT
    # size     | INTEGER
    # datetime | INTEGER
    try:
        cur.execute(
            """
            CREATE TABLE videolist (
                filename TEXT NOT NULL,
                directory TEXT,
                filetype TEXT,
                height INTEGER,
                width INTEGER,
                length TEXT,
                filesize INTEGER,
                datetime TEXT,
                PRIMARY KEY (directory, filename))
            """
        )
    except sqlite3.OperationalError:
        # すでにTABLEがある
        pass
    return


def main():
    # read target directories from json file.
    config = Path(environ["XDG_CONFIG_HOME"]) / "mp4indexer.json"
    data_dir = Path(environ["XDG_DATA_HOME"]) / "mp4index"
    # log_dir は $XDG_STATE_HOME が Ver.0.8から標準になった
    # $XDG_STATE_HOME がない場合は ~/.local/state が使われる
    log_dir = Path(environ["XDG_CACHE_HOME"])
    db_name = Path("mp4index.db")
    target_dirs = []
    try:
        with open(config, encoding="utf-8") as f:
            json_obj = json.load(f)
    except FileNotFoundError:
        target_dirs = [Path.cwd()]
        db_file = Path("./index-db.db")
        log_file = Path("./mp4indexer.log")
    else:
        try:
            target_dirs = json_obj["target_dirs"]
        except IndexError:
            target_dirs = [Path.cwd()]
        try:
            db_path = Path(json_obj["db_path"])
        except IndexError:
            db_path = data_dir
        try:
            db_name = Path(json_obj["index_db"])
        except IndexError:
            pass
        try:
            log_file = log_dir / Path(json_obj["logfile"])
        except IndexError:
            log_file = Path("./mp4indexer.log")

        if db_path:
            db_file = db_path / db_name
        else:
            db_file = data_dir / db_name

    parser = argparse.ArgumentParser(
        description="MP4ファイルのインデックスデータベースを生成する",
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
        "-d",
        "--debug",
        metavar="debug",
        action="store_const",
        const=1,
        default=0,
        help="Print Debug information",
    )
    args = parser.parse_args()

    # add log file handler to logger
    handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    create_table(cur)

    dirs = args.directories
    time_start = time.perf_counter()
    st = datetime.datetime.now()

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
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    main()
