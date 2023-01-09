#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# copyright (c) K.Fujii 2021,2022
# created : Mar 7, 2021
# last modified: Dec 24, 2022
"""
mp4find.py:
データベースからMP4ファイルを検索する
"""

import argparse
import sqlite3
import json
import re
import logging
from sys import exec_prefix
from ctypes import windll, wintypes, byref
from os import environ
from pathlib import Path

import cmigemo


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


def search_files(cur: sqlite3.Cursor, pattern: re.Pattern):
    # talbe videolist
    # ----------------------
    # filename    | TEXT
    # directory   | TEXT
    # filetype    | TEXT
    # height      | INTEGER
    # width       | INTEGER
    # length      | TEXT
    # filesize    | INTEGER
    # datetime    | TEXT
    # description | TEXT
    # keep        | INTEGER
    SQL = f"""SELECT * FROM videolist 
        WHERE filename REGEXP "{pattern.pattern}"
        OR description REGEXP "{pattern.pattern}"
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
        dtime = BRIGHT_CYAN + item["datetime"] + DEFAULT
        print(f'"{dirname}\\{fname}"\t{fsize}\t{dtime}')
        if desc:
            for s in desc:
                print(f"    {s}")


def main():
    # read target directories from json file.
    config = Path(environ["XDG_CONFIG_HOME"]) / "mp4indexer.json"
    data_dir = Path(environ["XDG_DATA_HOME"]) / "mp4index"
    # log_dir は $XDG_STATE_HOME が Ver.0.8から標準になった
    # $XDG_STATE_HOME がない場合は ~/.local/state が使われる
    db_name = Path("mp4index.db")
    try:
        with open(config, encoding="utf-8") as f:
            json_obj = json.load(f)
    except FileNotFoundError:
        db_path = Path("./index-db.db")
    else:
        try:
            db_name = Path(json_obj["index_db"])
        except IndexError:
            pass
        try:
            db_path = Path(json_obj["db_dir"]) / db_name
        except IndexError:
            db_path = data_dir / db_name

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
        "-v",
        "--invert",
        action="store_const",
        const=True,
        default=False,
        help="invert match",
    )
    parser.add_argument("-q", "--query", type=str, help="SQL query")
    parser.add_argument(
        "-t",
        "--type",
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
        logger.info(f"DB file: {args.DB}")
        db_path = args.DB

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    conn.load_extension(exec_prefix + "/DLLs/regexp.dll")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if args.query:
        pass
    else:
        color_console_enable()
        pat = compile_pattern(args.keyword[0])

        if args.type:
            for t in args.type:
                # TODO: list of types support
                pass

        result = search_files(cur, pat)
        pretty_print(result, pat)
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
