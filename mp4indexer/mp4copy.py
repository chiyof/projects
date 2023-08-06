# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
"""
mp4copy.py:
指定されたディレクトリのmp4ファイルを予め指定されたドライブ:ディレクトリに
コピーあるいは移動する。

mp4ファイルに対応する*.aacファイルがある場合、aacファイルを音声エンコード後に
remuxer（L-SMASH）でmuxしてからコピー/移動する。
コピー/移動が終わったらそれぞれのmp4ファイルのプロジェクトファイルを削除する。

・複数のファイルを指定できる
・ワイルドカードをサポートする

copyright (c) K.Fujii 2022
created : Sep 1, 2019
last modified: Aug 19, 2022
"""

import argparse
import logging
import random
import shutil
import string
from ctypes import byref, windll, wintypes
from pathlib import Path
from shutil import copy, move
from subprocess import run

from key2chapter import key2chapter
from send2trash import send2trash
from win32api import SetConsoleTitle

# import pdb; pdb.set_trace()

outdir = Path("m:/Videos/_new_coming")
mp4dir = Path("x:/Videos")
path = Path(".")
remuxer = Path("c:/Apps/aviutl/remuxer.exe")
qaac = Path("c:/Apps/aviutl/qaac64.exe")
without_ts = False

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"
DEFAULT = "\033[39m"


def color_console_enable():
    """Turn on colorized console."""
    INVALID_HANDLE_VALUE = -1
    # STD_INPUT_HANDLE = -10
    STD_OUTPUT_HANDLE = -11
    # STD_ERROR_HANDLE = -12
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    # ENABLE_LVB_GRID_WORLDWIDE = 0x0010

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


def randomname(len=8):
    """ランダムなファイル名（デフォルト長は8文字）を返す.

    Args:
        len (int): ファイル名の長さ
    Returns:
        (str): ファイル名
    """
    return "".join(random.choices(string.ascii_letters + string.digits, k=len))


def open_check(files):
    """ファイルがオープンされているかどうかを調べ、オープンされていれば処理対象から外す."""
    for f in files:
        if Path(f.stem + "_audio.m4a").exists():
            # エンコード中の判定
            files.remove(f)
            break
        else:
            try:
                """
                os.tmpnam()はテンポラリファイル名を取得してから実際に使用するまでの間に横取りされる
                セキュリティリスクがあるので、Python 3.0で削除されている。
                pathlibではファイルがオープンされているかどうかを調べる方法（is_opened()など）がないので、
                競合しないテンポラリファイル名を取得してそれをリネームすることでエラーが起きるかどうかを
                確認するという方法を取るが、リネームのタイミングで横取りされる可能性があるため、
                潜在的なリスクとなる。
                fileオブジェクトであればclosedプロパティを検査することで確認できるが、
                ファイルの内容を直接いじらずに検査することは難しい。
                次善の策としてテンポラリファイル名を別途生成してリネームし、成功するかどうかを見る。
                """
                opencheck = Path("tmptmp" + randomname(10) + ".mp4")
                f.rename(opencheck)
                opencheck.rename(f)
            except OSError:
                files.remove(f)

    for f in files:
        print("files:", f)
    return files


def encode_audio(file: Path):
    """Encode audio stream with qaac TrueVBR.

    qaacでTrueVBRエンコードする。
    qaac64 -V 127 *.aac -> *.m4a

    Args:
        file (Path): AACファイル
    Returns:
        (Path): m4aファイル名
    """
    if not file.with_suffix(".m4a").exists():
        cmd = f'{qaac} -V 127 "{file}"'
        logger.debug(cmd)
        run(cmd)
    return file.with_suffix(".m4a")


def remux_files(files):
    """MP4ファイルとAACファイルをremuxし、所定のディレクトリに移動・コピーする.

    Args:
        files (Path): mp4ファイル名のリスト
    Returns:
        None.
    """
    for mp4file in files:
        base = mp4file.stem
        aacfiles = list(path.glob(base.replace("[", "[[]") + "*.aac"))
        m4afiles = list(path.glob(base.replace("[", "[[]") + "*.m4a"))
        keyfile = base + ".keyframe"
        chapfile = base + ".chapter.txt"
        logger.debug(
            'mp4 = "%s", aacfiles = %s, m4afiles = %s', mp4file, aacfiles, m4afiles
        )
        tmp_video0 = Path(randomname() + ".mp4")
        tmp_audio1 = Path(randomname() + ".m4a")
        tmp_audio2 = Path(randomname() + ".m4a")
        tmp_chapter3 = Path(randomname() + ".chapter.txt")
        if len(aacfiles) != 0 or len(m4afiles) != 0:
            if len(m4afiles) == 0:
                for f in aacfiles:
                    m4afiles.append(encode_audio(f))
            # mp4box doesn't allow spaces in filename.
            logger.debug(f'copy "{mp4file}"" {tmp_video0}')
            logger.debug(f'copy "{m4afiles[0]}" {tmp_audio1}')
            if len(m4afiles) == 2:
                logger.debug(f'copy "{m4afiles[1]}" {tmp_audio2}')
            logger.debug(f'key2chapter "{keyfile}"')
            logger.debug(f'copy "{chapfile}" {tmp_chapter3}')

            copy(mp4file, tmp_video0)
            copy(m4afiles[0], tmp_audio1)
            if len(m4afiles) == 2 and Path(m4afiles[1]).exists():
                copy(m4afiles[1], tmp_audio2)
            if Path(keyfile).exists():
                key2chapter(keyfile)
            if Path(chapfile).exists():
                copy(chapfile, tmp_chapter3)
                chap_exists = True
            else:
                chap_exists = False
            # remux video file
            cmd = f'{remuxer} -i {tmp_video0} -i {tmp_audio1} -o "{mp4file}"'
            if len(m4afiles) == 2:
                # 二ヶ国語のとき
                logger.info("mux dual audio")
                cmd += f" -i {tmp_audio2}"
            else:
                logger.info("mux single audio")

            if chap_exists:  # chapterファイルがある場合
                cmd += f" --chapter {tmp_chapter3}"
            logger.debug(cmd)
            run(cmd, check=False)
        copy_file(mp4file, outdir)

        for f in [tmp_video0, tmp_audio1, tmp_audio2, tmp_chapter3]:
            try:
                f.unlink()
            except FileNotFoundError:
                pass

def copy_file(fname: Path, destdir: Path):
        # copy & move files
        base = Path(fname.name)
        if mp4dir.exists() and not without_ts:
            logger.info("copy %s to $MP4DIR", fname)
            try:
                copy(fname, destdir)
            except shutil.Error:
                input(BRIGHT_RED + f"{fname}はすでに存在しているためスキップします。" + DEFAULT)
            except FileNotFoundError:
                input(BRIGHT_YELLOW + f"{fname}は見つからないためスキップします。" + DEFAULT)
        if outdir.exists() and not without_ts:
            m2tsname = base.with_suffix(".m2ts")
            logger.info("move %s", m2tsname)
            try:
                move(m2tsname, outdir)
            except shutil.Error:
                input(BRIGHT_RED + f"{m2tsname}はすでに存在しているためスキップします。" + DEFAULT)
            except FileNotFoundError:
                input(BRIGHT_YELLOW + f"{m2tsname}は見つからないためスキップします。" + DEFAULT)
            except PermissionError:
                input(BRIGHT_YELLOW + f"{m2tsname}は他のプロセスで開かれているためスキップします。" + DEFAULT)

        logger.info("move %s", fname)
        try:
            move(fname, outdir)
        except shutil.Error:
            input(BRIGHT_RED + f"{fname}はすでに存在しているためスキップします。" + DEFAULT)
        except FileNotFoundError:
            input(BRIGHT_YELLOW + f"{fname}は見つからないためスキップします。" + DEFAULT)
        except PermissionError:
            input(BRIGHT_YELLOW + f"{fname}は他のプロセスで開かれているためスキップします。" + DEFAULT)

        for delfile in list(path.glob(base.stem.replace("[", "[[]") + "*")):
            logger.debug(f'send2trash "{delfile}"')
            try:
                send2trash(delfile)
            except FileNotFoundError:
                input(BRIGHT_YELLOW + f"{delfile}は見つからないためスキップします。" + DEFAULT)
            except PermissionError:
                input(BRIGHT_YELLOW + f"{delfile}は他のプロセスで開かれているためスキップします。" + DEFAULT)
            except OSError:
                input(BRIGHT_YELLOW + f"{delfile}は他のプロセスで開かれているためスキップします。" + DEFAULT)


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    parser = argparse.ArgumentParser(
        description="出力されたmp4ファイルを設定されたディレクトリにコピー＆移動する。\
                必要があれば音声MUXも行う。"
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
    parser.add_argument(
        "-t",
        "--wots",
        metavar="without_ts",
        action="store_const",
        const=True,
        default=False,
        help="Move MP4 file(s) without TS files.",
    )
    args = parser.parse_args()
    if args.wots:
        without_ts = True
    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    lockFile = Path.cwd() / "mp4copy.pid"
    if lockFile.exists():
        try:
            lockFile.unlink()
        except PermissionError:
            exit()
    else:
        color_console_enable()
        SetConsoleTitle(Path.cwd().name.replace("Enc-", ""))
        files = list(path.glob("*.mp4")) + list(path.glob("*.mkv"))

        files = open_check(files)

        try:
            with lockFile.open("w"):
                remux_files(files)
        except shutil.Error:
            pass
        finally:
            # lockfile should be removed even after exception is raised,
            # unless lockfile is locked by other process.
            lockFile.unlink()
