#!python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
"""
key2chapter.py:
カレントディレクトリからすべての.keyframeファイルを検索し
順次aviutl（muxer.exe, remuxer.exe）が取り込める形式の
チャプターマークに変換する。
ファイルが引数として指定された場合は、そのファイルだけを処理する。

TMPGEnc MPEG Smart Rendereの.keyframe 出力形式
[chap1]
Name=[チャプター名1]
[chap2]
Name=[チャプター名2]
ただし[chapx]はフレーム番号
チャプター名が明示的に指定されたときはName=の部分が使用される。

muxer / remuxer のチャプター形式
CHAPTER01=00:03:00.000
CHAPTER01NAME=タイトル1
CHAPTER02=00:06:30.000
CHAPTER02NAME=タイトル2
"""

import argparse
import logging
import sys
from dateutil.relativedelta import relativedelta

# from glob import glob
# from os.path import join, splitext
from pathlib import Path

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def key2chapter(keyfile):
    kffile = Path(keyfile)
    chapname = kffile.with_suffix(".chapter.txt")
    logger.debug("base: %s", chapname)
    try:
        with open(kffile, "r", encoding="utf-8") as f:
            with open(chapname, "w", encoding="utf-8") as outfile:
                lines = f.readlines()
                i = 0  # line number
                j = 1  # chapter number
                while i < len(lines):
                    chap = ""
                    s = lines[i].rstrip()
                    if s == "":  # skip blank line
                        i = i + 1
                        continue
                    if s.isdecimal():  # if line is frame number
                        rd = relativedelta(seconds=round(int(s) * 0.0333667))
                        chap = "{:02}".format(j)
                    if (i + 1) < len(lines):
                        if lines[i + 1][0] == "#":  # if next line is chapter name
                            chap = lines[i + 1].lstrip("#Name=").rstrip()
                            i = i + 1
                    time = "{0.hours:02}:{0.minutes:02}:{0.seconds:02}.000".format(rd)
                    outfile.write(f"CHAPTER{j:02}={time}\n")
                    outfile.write(f"CHAPTER{j:02}NAME={chap}\n")
                    i = i + 1
                    j = j + 1
    except FileNotFoundError:
        logger.error("keyframeファイルがありません: [%s]", kffile)
        return False
    except Exception as e:
        logger.error(e)
        return False
    finally:
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
        TMPGEnc MPEG Smart Renderer 5の出力する .keyframe ファイルを
        MP4Box が扱える .chapter.txt 形式に変換する
        """,
    )
    parser.add_argument(
        "files",
        metavar="files",
        type=str,
        nargs="*",
        help="files to convert from .kerframe to .chapter.txt",
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

    if args.debug == 1:
        logger.setLevel(logging.DEBUG)

    path = "."

    files = []
    i = 0
    logger.info(sys.argv)

    if len(args.files) == 0:
        p = Path(path)
        files = p.glob("*.keyframe")
    else:
        files = args.files

    logger.debug("files: %s", files)

    for file in files:
        key2chapter(file)
