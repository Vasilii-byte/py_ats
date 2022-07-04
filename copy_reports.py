#!/usr/bin/env python
# coding: utf-8

"""Скрипт по автоматическому копированию отчетов"""

import datetime as DT
import os
import glob
import shutil
from sys import platform

DEST_DIR = r"\\MSK1-TDMP01\Shared/Глушков/"

# Определение операционной системы
IS_UNIX = True
if platform == "linux" or platform == "linux2":
    IS_UNIX = True
elif platform == "win32":
    IS_UNIX = False


def convert_path(path, date1):
    """Конвертируем строку."""
    if IS_UNIX:
        path = path.replace("\\", "/")
    path = path.replace('%YEAR%', date1.strftime('%Y'))
    path = path.replace('%MONTH%', date1.strftime('%m'))
    path = path.replace('%DAY%', date1.strftime('%d'))
    return path


reports = []
rep = {'source': r"z:/BPE/Отдел покупок электроэнергии - RS/База отчетов/" + \
                 r"Публичные данные/Торговый график для РГЕ/%YEAR%/" + \
                 r"eur/%MONTH%/%DAY%/%YEAR%%MONTH%%DAY%_ROSEATOM_eur_sell_units.xls",
       'dest': r"ТГ РГЕ/"}
reports.append(rep)

rep = {'source': r"z:/BPE/Отдел покупок электроэнергии - RS/База отчетов/" + \
                 r"Публичные данные/Отчёт о торгах по субъектам РФ ЕЭС/" + \
                 r"%YEAR%/%YEAR%%MONTH%%DAY%_eur_trade_region_spub.xls",
       'dest': r"Торги в субъекте РФ/"}
reports.append(rep)

rep = {'source': r"i:/Персональный раздел АТС/40 СДД (ежедневные отчеты)/" + \
                 r"%YEAR%/%MONTH%/%DAY%/%YEAR%%MONTH%%DAY%_*_sdd_daily.xls",
       'dest': r"СДД/"}
reports.append(rep)

dt2 = DT.date.today()
dt1 = dt2 + DT.timedelta(days=-30)

for report in reports:
    dt = dt1
    while dt <= dt2:
        source_mask = report['source']
        source_mask = convert_path(source_mask, dt)

        dest = os.path.join(DEST_DIR, report['dest'])
        dest = convert_path(dest, dt)

        source_files = glob.glob(source_mask)

        for source_file in source_files:
            short_filename = os.path.basename(source_file)
            dest_filename = os.path.join(dest, short_filename)

            if (not os.path.exists(dest_filename)) and (os.path.exists(source_file)):
                shutil.copyfile(source_file, dest_filename)
                print("Файл {} скопирован".format(short_filename))
        dt = dt + DT.timedelta(days=1)
