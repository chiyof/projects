# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
# -*- coding: utf-8 -*-
#
# z2h_rename.py:
# ビデオファイル名の全角・半角を一括で変換する。ただし、
# ・局名は全角のままとする
# ・ファイル名として使用できない文字はエスケープする
# ・"[]"で囲まれた局名が含まれるファイル名のみを対象とする

import argparse
import logging
import re
from pathlib import Path

import jaconv

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

parser = argparse.ArgumentParser(
    description="""
        ファイル名の全角アルファベットおよび数字を半角に変換する。
        ただし、局名部分はいじらない。
        """
)
parser.add_argument(
    "target", metavar="target", type=str, nargs="*", default=".", help="対象ファイルまたはディレクトリ"
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
#
# 1. カレントディレクトリからファイル名を取得
target_files = []
for target in args.target:
    t = Path(target)
    if t.is_dir():
        for f in t.iterdir():
            if f.is_file():
                target_files.append(f)
    else:
        target_files.append(target)

logger.debug("files: %s", target_files)

# 2. []で囲まれた範囲を切り出す
#  a. 局名なら変数 TV_STATION に退避して、局名の文字列を'TV_STATION'に置換
#  b. [新]や[終]なら 変数NEW_MARKに退避して、該当文字列を'NEW_MARK'に置換
trans_dict = {
    "!": "！",
    "?": "？",
    ":": "：",
    ";": "；",
    "*": "＊",
    "/": "／",
    '"': "”",
    "<": "＜",
    ">": "＞",
    "|": "｜",
    "\\": "￥",
    "♯": "＃",
}
trans_tbl = str.maketrans(trans_dict)

for x in target_files:
    logger.debug("processing: %s", x)
    fname = x.name
    m = re.search("\\[.{3,15}?\\]\\.", fname)
    if m:
        logger.debug("station: %s", m.group(0))
        fname = fname.replace(m.group(0), "TV_STATION")
    # 3. 新ファイル名=jaconv.z2h(ファイル名, ascii=True, digit=True)で全角→半角変換
    new_name = jaconv.z2h(fname, ascii=True, digit=True, kana=False)
    new_name = new_name.replace("!?", "！？")
    new_name = new_name.translate(trans_tbl)
    new_name = re.sub("\\s+", " ", new_name)
    if m:
        fname = new_name.replace("TV_STATION", m.group(0))

    # 4. 新ファイル名を書き戻す
    if t != x:
        x.rename(fname)
