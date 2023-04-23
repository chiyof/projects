#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# copyright (c) K.Fujii 2021,2022
# created : Mar 7, 2021
# last modified: Feb 4, 2023
"""
mp4find.py:
データベースからMP4ファイルを検索する"""

import argparse
import json
import re
import logging
import time
from ctypes import windll, wintypes, byref
from os import environ
from pathlib import Path
from datetime import datetime, timedelta
from shutil import disk_usage
from typing import List

import cmigemo
import MySQLdb

__version__ = "0.5"


migemo_dict = "c:/Apps/bin/dict/base-dict"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"
DEFAULT = "\033[39m"


def color_console_enable():
    INVALID_HANDLE_VALUE = -1
    STD_INPUT_HANDLE = -10
    STD_OUTPUT_HANDLE = -11
    STD_ERROR_HANDLE = -12
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    ENABLE_LVB_GRID_WORLDWIDE = 0x0010

    hOut = windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    if hOut == INVALID_HANDLE_VALUE:
        return False
    dwMode = wintypes.DWORD()
    if windll.kernel32.GetConsoleMode(hOut, byref(dwMode)) == 0:
        return False
    dwMode.value |= ENABLE_VIRTUAL_TERMINAL_PROCESSING
    # dwMode.value |= ENABLE_LVB_GRID_WORLDWIDE
    if windll.kernel32.SetConsoleMode(hOut, dwMode) == 0:
        return False
    return True


def compile_pattern(S: str):
    logger.debug("Compiling pattern: %s", S)
    m = cmigemo.Migemo(migemo_dict)
    ret = m.query(S)
    logger.debug("regex = %s", ret)
    # return re.compile(ret, re.IGNORECASE)
    return ret


def search_files(cur, table_name: str, patterns: list, text: bool, regexp: bool):
    # TODO: check REGEXP perfomance

    if text:
        SEARCH_COLUMNS = """ CONCAT_WS(" ", directory, filename, description)"""
    else:
        SEARCH_COLUMNS = """ CONCAT_WS(" ", directory, filename)"""

    if not regexp:
        pat = f""" {SEARCH_COLUMNS} LIKE "%{patterns[0]}%" """
        if len(patterns) > 1:
            for p in patterns[1:]:
                pat += f""" AND {SEARCH_COLUMNS} LIKE "%{p}%" """
    else:
        # regexp only supports one argument.
        pat = f""" {SEARCH_COLUMNS} REGEXP "{compile_pattern(patterns[0])}" """

    SQL = f"SELECT * FROM {table_name} WHERE {pat}"
    if not text:
        SQL += """ AND (filetype="MP4" OR filetype="M2TS")"""
    logger.debug(SQL)
    cur.execute(SQL)
    data = cur.fetchall()
    result = [dict(d) for d in data]
    logger.debug(result)
    return result


def pretty_print(result: list, patterns: list, regexp: bool):
    match_list: List[re.Pattern] = []
    for p in patterns:
        match_list.append(re.compile(p))

    for item in result:
        dirname = item["directory"]
        fname = item["filename"]
        desc = item["description"]
        fsize = item["filesize"]
        length = item["length"]
        dtime = item["filedate"].strftime("%Y-%m-%d %H:%M:%S")
        framesize = (
            (BRIGHT_BLUE + f'{item["width"]}x{item["height"]}' + DEFAULT)
            if item["width"] > 0
            else ""
        )
        for rx in match_list:
            if res := rx.search(dirname):
                dirname = rx.sub(BRIGHT_YELLOW + res.group() + DEFAULT, dirname)
            if res := rx.search(fname):
                fname = rx.sub(BRIGHT_GREEN + res.group() + DEFAULT, fname)
            if res := rx.search(desc):
                desc = rx.sub(
                    BRIGHT_MAGENTA + res.group() + DEFAULT, desc, re.MULTILINE
                )
        print(f'"{dirname}/{fname}"\t{framesize}\t{length}\t{fsize}\t{dtime}')
        if desc != "":
            for line in desc.split("\n"):
                if "\033" in line:
                    print(f"    {line}")


def show_query_time(start_time: float):
    end_time = time.perf_counter()
    time_diff = end_time - start_time
    time_ellaps = time.gmtime(time_diff)
    logger.info(
        "query in : %02d:%02d:%02d.%04d",
        time_ellaps.tm_hour,
        time_ellaps.tm_min,
        time_ellaps.tm_sec,
        (time_diff - int(time_diff)) * 1000,
    )


def show_disk_info(drive: str):
    (total, used, free) = disk_usage(drive)
    free_tb = free / 1024**4
    used_percent = used / total * 100
    logger.info(
        f"""drive {drive.upper()} {str.format("{:.2f}", free_tb)}TB free"""
        f""" ({str.format("{:.1f}",used_percent)}% used)"""
    )


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
    if (db_name := config.get("db_name")) is None:
        db_name = "mp4index.db"
    if (table_name := config.get("table_name")) is None:
        table_name = "videolist"

    parser = argparse.ArgumentParser(
        description="MP4データベースからタイトルを検索する",
        #    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "keywords",
        type=str,
        nargs="+",
        help="search word for search video files",
    )
    parser.add_argument(
        "-t",
        "--text",
        action="store_const",
        const=True,
        default=False,
        help="also search into text files",
    )
    parser.add_argument(
        "-q",
        "--query",
        type=str,
        help="print SQL query phrase",
    )
    parser.add_argument(
        "-c",
        "--codec",
        type=str,
        action="append",
        nargs="+",
        help="specify codec type(s)",
    )
    parser.add_argument(
        "-r",
        "--regexp",
        action="store_const",
        const=True,
        default=False,
        help="enable regexp search (supports only one pattern)",
    )
    parser.add_argument(
        "-D",
        "--DB",
        type=str,
        help="specify database",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=__version__,
    )
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

    if args.debug:
        logger.setLevel(logging.DEBUG)
        print(args)

    logger.debug(args)

    if args.DB:
        logger.info(f"DB name: {args.DB}")
        db_name = args.DB

    conn = MySQLdb.connect(host=db_host, user=db_user, passwd=db_pass, database=db_name)
    cur = conn.cursor(MySQLdb.cursors.DictCursor)
    start_time = time.perf_counter()
    if args.query:
        pass
    else:
        color_console_enable()

        if args.codec:
            for t in args.codec:
                # TODO: list of types support
                pass

        result = search_files(cur, table_name, args.keywords, args.text, args.regexp)
        pretty_print(result, args.keywords, args.regexp)
        print("")
        show_query_time(start_time=start_time)
        show_disk_info("m:")
    conn.close()


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    main()
