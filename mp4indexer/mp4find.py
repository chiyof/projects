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
データベースからMP4ファイルを検索する
"""

import argparse
import json
import re
import logging
from sys import exec_prefix
from ctypes import windll, wintypes, byref
from os import environ
from pathlib import Path
from datetime import datetime
from shutil import disk_usage

import cmigemo
import MySQLdb


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
    # return ret
    return re.compile(ret, re.IGNORECASE)


def search_files(cur, table_name: str, pattern: re.Pattern, text: bool):
    # TODO: check REGEXP perfomance
    SQL = f"SELECT * FROM {table_name}"
    if not text:
        SQL += f"""
            WHERE (filetype="MP4" OR filetype="M2TS")
            AND CONCAT(directory, filename) REGEXP "{pattern.pattern}"
        """
    else:
        SQL = f"""
            WHERE CONCAT(directory, filename, description) REGEXP "{pattern.pattern}"
        """
    cur.execute(SQL)
    data = cur.fetchall()
    result = [dict(d) for d in data]
    logger.debug(result)
    return result


def pretty_print(result: list, pat: re.Pattern):
    for item in result:
        desc = []
        if res := pat.search(item["directory"]):
            dirname = pat.sub(BRIGHT_YELLOW + res.group() + DEFAULT, item["directory"])
        else:
            dirname = item["directory"]
        if res := pat.search(item["filename"]):
            fname = pat.sub(BRIGHT_YELLOW + res.group() + DEFAULT, item["filename"])
        else:
            fname = item["filename"]
        for line in item["description"].split("\n"):
            if res := pat.search(line):
                desc.append(pat.sub(BRIGHT_YELLOW + res.group() + DEFAULT, line))
        fsize = BRIGHT_BLUE + f'{item["width"]}x{item["height"]}' + DEFAULT
        length = f'{item["length"]}'
        dtime = item["datetime"].strftime("%Y-%m-%d %H:%M:%S")
        print(f'"{dirname}/{fname}"\t{fsize}\t{length}\t{dtime}')
        if desc:
            for s in desc:
                print(f"    {s}")


def show_disk_info(drive: str):
    (total, used, free) = disk_usage(drive)
    free_tb = free / 1024**4
    used_percent = used / total * 100
    print(
        f"""\ndrive {drive.upper()} {str.format("{:.2f}", free_tb)}TB free"""
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
        db_user = "kats"
    if (db_pass := config.get("db_pass")) is None:
        db_pass = "sanadamitsuki"
    if (db_name := config.get("db_name")) is None:
        db_name = "mp4index.db"
    if (table_name := config.get("table_name")) is None:
        table_name = "videolist"

    parser = argparse.ArgumentParser(
        description="MP4データベースからタイトルを検索する",
        #    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "keyword",
        type=str,
        nargs="*",
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
    parser.add_argument("-q", "--query", type=str, help="SQL query")
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
        help="enable regexp search",
    )
    parser.add_argument("-D", "--DB", type=str, help="specify database")
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
    if args.query:
        pass
    else:
        color_console_enable()
        pat = compile_pattern(args.keyword[0])

        if args.codec:
            for t in args.codec:
                # TODO: list of types support
                pass

        result = search_files(cur, table_name, pat, args.text)
        pretty_print(result, pat)
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
