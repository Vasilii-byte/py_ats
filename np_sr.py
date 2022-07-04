#!/usr/bin/env python
# coding: utf-8

"""Скрипт по загрузке данных с сайта НП СР."""
import re
import os
import requests


SITE_URL = "http://www.np-sr.ru"
VIE_URL = SITE_URL + "/ru/market/vie/index.htm"
REPORT_PATH = os.path.normpath(
    r"z:\BPE\Отдел покупок электроэнергии - RS\База отчетов\НП Совет рынка"
)

s = requests.Session()
response = s.get(VIE_URL, verify=False)

RE_EXPR = r"href=\"(/sites/default/files/reestr[_a-z\d.]*?.xlsx?)\""
results = re.findall(RE_EXPR, response.text)

if results is not None:
    for ref in results:
        if "reestr_kvalificirovannyh" in ref:
            REPORT_DIR = os.path.join(
                REPORT_PATH, "Перечень квалифицированных объектов"
            )
        elif "reestr_sertifikatov" in ref:
            REPORT_DIR = os.path.join(REPORT_PATH, "Реестр сертификатов")
        else:
            REPORT_DIR = None

        if REPORT_DIR is not None:
            if not os.path.exists(REPORT_DIR):
                os.makedirs(REPORT_DIR)

            filename = ref.split("/")[-1]
            full_filename = os.path.join(REPORT_DIR, filename)
            if not os.path.exists(full_filename):
                try:
                    FILE_URL = SITE_URL + ref

                    response = s.get(FILE_URL, verify=False)
                    if response.status_code != 200:
                        print(
                            "Bad response with loading file %s. \
                                        Response code %s",
                            os.path.basename(filename),
                            response.status_code,
                        )
                except requests.exceptions.RequestException as exception:
                    print(exception)

                print("Файл: {}".format(filename))

                try:
                    with open(full_filename, "wb") as report_file:
                        report_file.write(response.content)
                except IOError as exception:
                    print("Error with saving file %s", filename)
