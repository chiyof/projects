# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
# -*- coding: utf-8 -*-
#
# copyright (c) K.Fujii 2021
# created : Jul 26, 2021
# last modified: May 22, 2022
# Changelog:
"""rename_videofiles.py: ビデオファイル名の不要部分（＜アニメギルド＞など）を一括で編集削除する.

'[新]' あるいは '[終]' があれば、放送局名の直前に移動する
"""

import argparse
import logging
import re
from pathlib import Path

import jaconv

debug = False
z2h = False  # 全角アルファベットと数字を半角にするかどうか

# 削除する文字列。正規表現も使用できる。
del_words = [
    "\\[初\\]",
    "\\[無\\]",
    "＜アニメギルド＞",
    "[【 ]アニメイズム[】 ]",
    "[【 ]スーパーアニメイズム[】 ]",
    "【ヌマニメーション】",
    "スーパーアニメイズム",
    "アニメイズム",
    "アニメA・",
    "アニメＡ・",
    "アニメ女子部",
    "＜ノイタミナ＞",
    "＜＋Ｕｌｔｒａ＞",
    "アニメの神様",
    "（天てれアニメ）",
    "(TV|ＴＶ|ミニ|テレビ)*アニメ",
    "BS11ガンダムアワー",
    "ＡｎｉｃｈＵ",
    "AnichU",
    "日５",
    "【ANiMAZiNG!!!】",
    "【ＡＮｉＭＡＺｉＮＧ！！！】",
]

new_end_words = ["[新]", "[終]"]

# ファイル名に使用できない半角文字、井桁とシャープなど、
# 置き換えする文字列
trans_dict = str.maketrans(
    {
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
        ":": "：",
    }
)

# 処理時には出現順序が入れ替わらないように注意
audio_words = ["[二]", "[多]", "[SS]", "[Ｓ]", "[吹]", "[解]", "[字]", "[再]"]

"""処理手順
 1. files に格納されたTSファイルを取り出し、
    最初の '.' までを trim として切り出す
    ただし、録画中などopen中のファイルは弾く
 2. trim に del_words の中で一致するものがあれば削除する
 3. '[新]' あるいは '[終]' があれば new_end_mark として待避し、trim から削除する
 4. 行頭に [] で囲まれた部分があれば退避する
 5. 放送局名を切り出して station に保存する
 6. z2h フラグに応じて jaconv.z2h でファイル名の全角→半角変換
 7. trim + new_end_mark + station を新しいファイル名とする
 8. '.ts', '.ts.err', '.ts.program.txt' の三種のファイルについてすべて同様に名前変更する

ファイル名の構文解析:
    [初][新][無][終][多]＜タイトル＞[新][終]＜話数＞[新][終]＜サブタイトル＞[新][終][二][字][多] ＜局名＞.*

変更後:
　　[映]＜タイトル＞ ＜話数＞＜サブタイトル＞[新][終][二][字][多][SS] ＜局名＞.*
"""


def rename_files():
    trans_tbl = str.maketrans(trans_dict)

    # 1. カレントディレクトリからTSファイル名を取得
    # リネームは録画終了したファイルのみを対象とする
    # 録画が終了していれば .ts.err ファイルが生成されているのでそれを使用する
    if len(args.files) == 0:
        files = list(Path(".").glob("*.ts.err"))
    else:
        files = args.files

    for f in files:
        new_end_mark = ""
        header_mark = ""
        audio_mark = ""
        station = ""
        # 1. 最初のピリオドより左の部分を切り出す
        # "[無][初][新]番組名　＃１「サブタイトル」[二][字] [放送局名].ts.err"
        body = str(f).rstrip(".ts.err")
        # 最後のrenameのために退避する
        # "[無][初][新]番組名　＃１「サブタイトル」[二][字] [放送局名]"
        orig_name = body
        # 2. body に del_words の中で一致するものがあれば削除する
        for s in del_words:
            body = re.sub(s, "", body)
        # "[新]番組名　＃１「サブタイトル」[二][字] [放送局名]"
        # 3. '[新]'や'[終]'があれば、変数 new_end_mark に退避して削除
        for s in new_end_words:
            if body.find(s) >= 0:
                body = body.replace(s, "　")
                new_end_mark = s
        # "　番組名　＃１「サブタイトル」[二][字] [放送局名]"
        # 4. '[二]'や'[多]'などがあれば、変数 audio_mark に退避して削除
        # 同時に'[二]'と'[SS]'があった場合などのために連結する
        # TODO: 順序をキープしたい
        for s in audio_words:
            if body.find(s) >= 0:
                body = body.replace(s, "")
                audio_mark += s
        print(f"audio--{audio_mark}--")
        # "　番組名　＃１「サブタイトル」[字] [放送局名]"
        # 5. それ以外に[]で囲まれた部分があれば header_mark に退避
        # （'[映]'など）
        m = re.search("^\\[.+?\\]+?", body)
        if m:
            header_mark = m.group(0)
            body = body.replace(header_mark, "")
            logger.debug("header_mark : %s", header_mark)
        # "　番組名　＃１「サブタイトル」 [放送局名]"
        # 6. 最後に残った局名を変数 station に退避する
        m = re.search("\\[.+\\]", body)
        if m:
            station = m.group(0)
            body = body.replace(station, "")
            logger.debug("station: %s", station)
        # "　番組名　＃１「サブタイトル」 "
        # 7. z2h が True なら新ファイル名=jaconv.z2h(ファイル名, ascii=True, digit=True)で全角→半角変換
        body = jaconv.z2h(body, ascii=True, digit=True, kana=False) if z2h else body
        # 半角 "!" はそのままにしたいので、"!?" のみ "！？" に置換する
        # 2文字なので translate() できないので個別処理
        body = body.replace("!?", "！？")
        # 半角にしない文字およびおかしな文字の修正（"♯"など）
        body = body.translate(trans_tbl)
        # 8. 空白の処理
        # 行頭行末にある空白は削除
        body = body.strip()
        # "番組名　＃１「サブタイトル」"
        # bodyの最後が "」" か"）"以外なら空白1つ追加
        if not body.endswith(("」", "）")):
            body += " "
        # "番組名　＃１「サブタイトル」"
        # 9. 複数の空白を１つにまとめ、新ファイル名を生成する
        new_name = re.sub(
            "[\\s　][\\s　]+",
            " ",
            header_mark + body + new_end_mark + audio_mark + " " + station,
        )
        # "番組名　＃１「サブタイトル」 [新][二][字] [放送局名]"
        # 10. '.ts', '.ts.err', '.ts.program.txt' の三種のファイルについてすべて同様に名前変更する
        if debug:
            print(orig_name, "->", new_name)
        else:
            for sfx in [".ts", ".ts.err", ".ts.program.txt"]:
                try:
                    p = Path(orig_name + sfx)
                    if p.exists():
                        p.rename(new_name + sfx)
                except Exception as e:
                    print(e)


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
    ビデオファイル名の不要部分（＜アニメギルド＞など）を一括で編集削除する
    '[新]' あるいは '[終]' があれば、放送局名の直前に移動する
    """
        #    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "files",
        metavar="files",
        type=str,
        nargs="*",
        help="files to be parsed its name and to be renamed",
    )
    parser.add_argument(
        "-z",
        "--zenhan",
        metavar="z2h",
        action="store_const",
        const=1,
        default=0,
        help="Convert Zenkaku to Hanhaku except Station name",
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

    if args.debug:
        logger.setLevel(logging.DEBUG)
        debug = True
    if args.zenhan:
        logger.info("Zenkaku -> Hankaku convert.")
        z2h = True

    rename_files()
