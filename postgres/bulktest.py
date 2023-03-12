#!python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8 ff=unix ft=python ts=4 sw=4 sts=4 si et fdm fdl=99:
# vim:cinw=if,elif,else,for,while,try,except,finally,def,class:
#
# created on Mar.12, 2023
"""
bulktest.py:
PostgreSQL + psycopg2 の環境で、大量にデータをインサートする際の
単純な insert と psycopg2.extras の execute_values によるバルクインサートの
パフォーマンスを計測する
"""
import logging
import time
from datetime import datetime
from random import randint
from typing import List

import loremipsum
import psycopg2
import psycopg2.extras
from tqdm import tqdm


class DbData:
    """データを扱いやすくするためのデータオブジェクトクラス"""

    def __init__(self):
        self.id = None
        self.sentence = None
        self.number = None
        self.created = None

    def __str__(self):
        return self.__dict__

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


def simple_insert(conn, table, data: List[DbData]):
    """通常の insert によるレコード挿入

    Args:
        conn (_type_): connectionオブジェクト
        table (_type_): テスト用テーブル
        data (_type_): データのリスト
    """
    SQL = f"INSERT INTO {table} (sentence, number, created) VALUES (%s, %s, %s)"
    with conn.cursor() as cur:
        for d in data:
            cur.execute(SQL, (d.sentence, d.number, d.created))


def bulk_insert(conn, table, data):
    """psycopg2.extras.execute_values()によるバルクインサート

    Args:
        conn (_type_): connectionオブジェクト
        table (_type_): テスト用テーブル
        data (_type_): データのリスト
    """
    SQL = f"INSERT INTO {table} (sentence, number, created) VALUES %s"
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, SQL, data)


def create_table(conn, table):
    """テスト用のテーブル作成

    Args:
        conn (_type_): connectionオブジェクト
        table (_type): テーブル名
    """
    SQL = f"CREATE TABLE IF NOT EXISTS {table} (id SERIAL NOT NULL, sentence TEXT, \
        number INTEGER, created TIMESTAMP, PRIMARY KEY (id))"
    with conn.cursor() as cur:
        cur.execute(SQL)


def print_time(msg, time_start, time_end):
    """実行時間計測用

    Args:
        msg (str): 計測対象を明示する文字列
        time_start (float): 開始時刻
        time_end (float): 終了時刻
    """
    time_diff = time_end - time_start
    time_ellapsed = time.gmtime(time_diff)
    logger.info(
        f"{msg} took %02d:%02d:%02d.%04d",
        time_ellapsed.tm_hour,
        time_ellapsed.tm_min,
        time_ellapsed.tm_sec,
        (time_diff - int(time_diff)) * 1000,
    )


def main():
    dsn = "postgres://kats:password@localhost:5432/testdb"
    conn = psycopg2.connect(dsn)
    table = "test1"
    create_table(conn, table)

    logger.info("preparing data for simple_insert.")
    time_start = time.perf_counter()
    data: List[DbData] = []
    n = 10000
    # lorem ipsum は時間がかかりすぎるので、固定文字列にしてnを増やしたほうがいいかも。
    for cs, cw, s in tqdm(loremipsum.generate_paragraphs(n), total=n):
        d = DbData()
        d.id = 0
        d.sentence = s.replace("'", "")
        d.number = randint(0, 100000)
        d.created = datetime.now()
        data.append(d)
    time_end = time.perf_counter()
    print_time("preparing for simple_insert", time_start, time_end)

    time_start = time.perf_counter()
    simple_insert(conn, table, data)
    conn.commit()
    time_end = time.perf_counter()
    print_time("simple_insert", time_start, time_end)

    logger.info("preparing data for bulk_insert.")
    time_start = time.perf_counter()
    # id は SERIAL NOT NULLなので、idを指定せずに登録することで勝手にidを振られるようにする
    # execute_values()が受け取るデータはタプルなので、タプルのリストに変換する
    data_list = [tuple(v for k, v in d.__dict__.items() if k != "id") for d in data]
    time_end = time.perf_counter()
    print_time("preparing for bulk_insert", time_start, time_end)

    time_start = time.perf_counter()
    bulk_insert(conn, table, data_list)
    conn.commit()
    time_end = time.perf_counter()
    print_time("bulk_insert", time_start, time_end)


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(name)-12s %(levelname)-8s %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    main()
