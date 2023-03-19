#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# copyright (c) K.Fujii 2021,2022
# created : Mar 7, 2021
# last modified: Feb 4, 2023
"""
mp4indexer.py:
指定されたディレクトリからMP4ファイルの情報を収集してDBに登録する
対象ディレクトリは mp4indexer.json にて指定する
動画ファイルではフレームサイズや長さも登録する

音声多重（含む二ヶ国語）の場合には、
"decode_pce: Input buffer exhausted before END element found"
というエラーがopencvから出力されるが、出力の抑制は出来ない模様
"""

import argparse
import json
import math
import logging
import time
import datetime
from os import environ
from pathlib import Path
from subprocess import run

import MySQLdb
import cv2

logger = logging.getLogger(__name__)


class VideoData:
    """ビデオの情報をプロパティ化してアクセスしやすくするためのクラス"""

    def __init__(self):
        self.__width = 0
        self.__height = 0
        self.__length = 0
        self.__fourcc = ""

    @property
    def width(self):
        """フレームサイズ（横）"""
        return self.__width

    @property
    def height(self):
        """フレームサイズ（縦）"""
        return self.__height

    @property
    def length(self):
        """再生時間"""
        return self.__length

    @property
    def fourcc(self):
        """ビデオエンコーダ

        HEV1、AVC1、MPEGなど
        """
        return self.__fourcc

    @width.setter
    def width(self, width):
        self.__width = width

    @height.setter
    def height(self, height):
        self.__height = height

    @length.setter
    def length(self, length):
        self.__length = length

    @fourcc.setter
    def fourcc(self, fourcc):
        self.__fourcc = fourcc


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
    v_data = VideoData()

    video_track = cv2.VideoCapture(str(fname))
    v_data.width = video_track.get(cv2.CAP_PROP_FRAME_WIDTH)
    v_data.height = video_track.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fcc_int = int(video_track.get(cv2.CAP_PROP_FOURCC))
    v_data.fourcc = "".join(list(fcc_int.to_bytes(4, "little").decode("utf-8"))).upper()
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
    v_data.length = length
    if v_data.width == 0 or v_data.height == 0:
        logger.warn(
            f"invalid frame size: width {v_data.width} height {v_data.height} on {fname}"
        )

    return v_data


def remove(conn: MySQLdb.Connection, cur, tablename: str):
    """DBのデータから keep == 2 のレコードを検索し、ファイルが実在すれば削除する

    Args:
        con (sqlite3.Connection): _description_
        cur (sqlite3.Cursor): _description_

    """
    count = 0
    SQL = f"SELECT * FROM {tablename} WHERE filtype='M2TS' and keep=2"

    cur.execute(SQL)
    res = cur.fetchall()
    for r in res:
        if r.keep == 2:
            p = Path(r["directory"], r["filename"])
            if p.exists():
                Path.unlink(p, missing_ok=True)
                count += 1
                logger.info(f"removed : {p}")
            else:
                logger.warn(f"remove: {p} does not exist")
            SQL = f"""
                delete from {tablename}
                where directory="{r['directory']}"
                and filename="{r['filename']}"
            """
            cur.execute(SQL)
            conn.commit()
    return count


def cleanup(conn: MySQLdb.Connection, cur, tablename: str):
    """DBのデータが示すファイルが存在するかどうかを確認し、存在しなければDBからレコードを削除する

    Args:
        con (sqlite3.Connection): _description_
        cur (sqlite3.Cursor): _description_

    """
    count = 0
    SQL = f"SELECT * FROM {tablename}"

    # res = cur.execute(SQL) とすると、forループが最初のexecute()で終わる
    # おそらく res が壊れるので、横着せずにfetchall()すること。
    cur.execute(SQL)
    res = cur.fetchall()
    for r in res:
        p = Path(r["directory"], r["filename"])
        if p.exists():
            continue
        else:
            logger.info(f"clean-up {p}")
            SQL = f"""
                delete from {tablename}
                where directory="{r['directory']}"
                and filename="{r['filename']}"
            """
            count += 1
            cur.execute(SQL)
            conn.commit()
    return count


def index_files(p: Path, conn: MySQLdb.Connection, cur, tablename: str):
    """Get video info from the video file using OpenCV"""
    v_data = VideoData()
    if p.is_file():
        target = [p]
    else:
        target = p.glob("**/*")
    for f in target:
        if f.is_dir():
            logger.debug(f)
            conn.commit()
            continue
        f = f.absolute()
        # dirname = str(f.parent).replace("'", "''")
        dirname = f.parent.as_posix()
        # fname = f.name.replace("'", "''")
        fname = f.name
        fsize = f.stat().st_size
        filetype = f.suffix.upper()[1:]
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
                SELECT * FROM {tablename} WHERE filename="{fname}"
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
            if filetype in ["MP4", "M2TS", "M2T", "MPG", "TS", "AVI", "MKV"]:
                # ビデオファイル
                logger.debug(f"updating {fname}")
                v_data = get_video_info(f)
                if v_data.length != 0:
                    play_length = time.strftime(
                        "%H:%M:%S", time.gmtime(math.ceil(v_data.length))
                    )
                else:
                    play_length = 0
                if filetype in ["M2TS", "M2T", "TS", "MPG"]:
                    v_data.fourcc = "MPEG"
                SQL = f"""
                    INSERT INTO {tablename} 
                        (filename, directory, filetype, height, width,
                         length, filesize, fourcc, datetiem, description, keep)
                    VALUES ("{fname}", "{dirname}", "{filetype}",
                        {v_data.height}, {v_data.width}, "{play_length}",
                        {fsize}, "{v_data.fourcc}", "{timestamp}", "", 0)
                    ON DUPLICATE KEY
                    UPDATE height = {v_data.height}, width = {v_data.width},
                        length = "{play_length}", datetime = "{timestamp}", filesize = {fsize}
                    RETURNING filename
                    """
            elif filetype in ["TXT"]:
                logger.debug(f"updating {fname}")
                try:
                    description = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning(f"Unicode decoding error: {fname}")
                    logger.info("run nkf to encode to UTF-8")
                    cmd = ["nkf", "-w", "--overwrite", "--in-place", f"{f}"]
                    logger.debug(cmd)
                    res = run(cmd, capture_output=True)
                    logger.debug("return code: {}".format(res.returncode))
                    logger.debug("output: {}".format(res.stdout.decode()))
                    logger.debug("output: {}".format(res.stderr.decode()))
                    description = f.read_text(encoding="utf-8")
                description = description.replace("'", "''").replace('"', '""')
                SQL = f"""INSERT INTO {tablename} VALUES ("{fname}", "{dirname}", "{filetype}",
                        0, 0, "",
                        {fsize}, "", "{timestamp}", "{description}", 0)
                    ON DUPLICATE KEY
                    UPDATE datetime = "{timestamp}", filesize = {f.stat().st_size}, description = "{description}"
                    RETURNING filename
                    """
            else:
                logger.info(f"unknown suffix : {f.parent}\\{fname}")

                SQL = f"""INSERT INTO {tablename} VALUES ("{fname}", "{dirname}", "{filetype}",
                    0, 0, "", {fsize}, "", "{timestamp}", "", 0)
                    ON DUPLICATE KEY
                    UPDATE filename = filename
                    RETURNING *
                    """

            try:
                cur.execute(SQL)
            except MySQLdb.OperationalError as e:
                print(e)
                logger.error(SQL)
                exit(-1)
            except MySQLdb.ProgrammingError as e:
                print(e)
                logger.error(SQL)
                exit(-1)
            else:
                res = cur.fetchall()
                if res is None:
                    logger.warn(f"insertion failed: {fname}")
                else:
                    logger.debug(f"inserted {dirname}/{fname}")
        conn.commit()


def create_table(cur, tablename: str):
    # talbe videolist
    # ----------------------
    # filename    | VARCHAR(255)
    # directory   | VARCHAR(255)
    # filetype    | CHAR(8)
    # height      | INT UNSIGNED
    # width       | INT UNSIGNED
    # length      | CHAR(8)
    # filesize    | BIGINT
    # fourcc      | CHAR(4)
    # datetime    | TIMESTAMP
    # description | TEXT
    # keep        | TINYINT (0: default, 1: keep, 2: remove)
    try:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {tablename} (
                filename varchar(255) NOT NULL,
                directory varchar(255) NOT NULL,
                filetype char(8) NOT NULL DEFAULT "",
                height INT unsigned NOT NULL DEFAULT 0,
                width INT unsigned NOT NULL DEFAULT 0,
                length char(8) DEFAULT "",
                filesize bigint unsigned NOT NULL DEFAULT 0,
                fourcc CHAR(4) DEFAULT "",
                datetime timestamp default 0,
                description TEXT DEFAULT "",
                keep tinyint default 0,
            PRIMARY KEY (directory, filename))
            """
        )
    except MySQLdb.OperationalError:
        # すでにTABLEがある
        pass
    return


def main():
    # read target directories from json file.
    config = {}
    config_file = Path(environ["XDG_CONFIG_HOME"]) / "mp4indexer.json"
    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        pass
    if (db_host := config.get("db_host")) is None:
        db_host = "192.168.10.4"
    if (db_user := config.get("db_user")) is None:
        db_user = "username"
    if (db_pass := config.get("db_pass")) is None:
        db_pass = "password"
    if (target_dirs := config.get("target_dirs")) is None:
        target_dirs = [Path.cwd()]
    if (log_dir := config.get("log_dir")) is None:
        log_dir = environ["XDG_DATA_HOME"] + "/mp4indexer"
    if (db_name := config.get("db_name")) is None:
        db_name = "mp4index.db"
    if (tablename := config.get("table_name")) is None:
        tablename = "videolist"
    # log_dir は $XDG_STATE_HOME が Ver.0.8から標準になった
    # $XDG_STATE_HOME がない場合は ~/.local/state が使われる
    log_name = Path(log_dir).joinpath(time.strftime("mp4index-%Y-%m-%d.log"))

    parser = argparse.ArgumentParser(
        description="""
            MP4ファイルのインデックスデータベースを生成する
            keepフラグ: 0=キープしない, 1=キープする, 2=エラー切り貼り用, 3=削除する
        """,
        epilog=f"""指定がない場合のデフォルトターゲット: {target_dirs}""",
        # formatter_class=smartformatter.SmartFormatter,
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
        action="store_true",
        default=False,
        help="Clean up database",
    )
    parser.add_argument("-D", "--DB", type=Path, help="specify database")
    parser.add_argument(
        "-r",
        "--remove",
        action="store_true",
        default=False,
        help="remove video files of which 'keep' flag is 2",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Print Debug information",
    )
    args = parser.parse_args()

    # add log file handler to logger
    fh = logging.FileHandler(log_name, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.DB:
        logger.info(f"DB name: {args.DB}")
        db_name = args.DB

    logger.debug(target_dirs)
    conn = MySQLdb.connect(
        host=db_host, user=db_user, password=db_pass, database=db_name
    )
    cur = conn.cursor(MySQLdb.cursors.DictCursor)
    create_table(cur, tablename)

    dirs = args.directories
    time_start = time.perf_counter()
    st = datetime.datetime.now()

    if args.cleanup:
        result = cleanup(conn, cur, tablename)
        logger.info(f"{result} records were deleted.")
    elif args.remove:
        result = remove(conn, cur, tablename)
        logger.info(f"{result} files were removed.")
    else:
        for d in dirs:
            p = Path(d)
            if not p.exists():
                logger.info("%s is not exist", p)
            else:
                index_files(p, conn, cur, tablename)

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
