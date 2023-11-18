# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
# -*- coding: utf-8 -*-
#
"""
k2n_filenames.py:
ビデオファイル名の漢数字を一括でアラビア数字に変換する。

漢数字のパターンは、"([一二三四五六七八九壱弐参十][一二三四五六七八九〇壱弐参十]*)"で
"([話章説])"があとに続くものとする。
パターンはリテラル kansuji で指定する。
"""

import argparse
import logging
import re
from pathlib import Path
from os import rename

from jaconv import h2z
from kanjize import kanji2int


# 置換する漢数字のパターン指定
kansuji = "([一二三四五六七八九壱弐参十][一二三四五六七八九〇壱弐参十]*)"
suffix = "([話章説夜幕])"
pattern = kansuji + suffix
workdir = "."


def k2n_replace(name):
    """
    patternでマッチする部分を切り出し、グループ分けして漢数字だけを取り出し、
    漢数字を全角アラビア数字に変換する
    """
    match = re.search(pattern, name)
    if match:
        repl = "{}{}".format(
            h2z(str(kanji2int(match.group(1))), digit=True), match.group(2)
        )
        new_name = re.sub(match.group(0), repl, name)
        return new_name
    else:
        return name


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    parser = argparse.ArgumentParser(
        description="""
            ファイル名に含まれる漢数字をアラビア数字に変換する。
            """
    )
    parser.add_argument("files", metavar="files", type=str, nargs="*", help="対象ファイル")
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

    # カレントディレクトリからファイル名を取得
    if len(args.files) == 0:
        p = Path(workdir)
        files = list(p.glob("*"))
    else:
        files = args.files

    for f in files:
        if f.is_file():
            name = str(f)
            new_name = k2n_replace(name)
            # 新ファイル名を書き戻す
            if name != new_name:
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(
                        "%s\n                                           -> %s",
                        name,
                        new_name,
                    )
                else:
                    try:
                        rename(name, new_name)
                    except OSError as e:
                        print(e)
