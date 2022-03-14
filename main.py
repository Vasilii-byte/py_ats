#!/usr/bin/env python
# coding: utf-8

"""Скрипт по загрузке данных с сайта АО "АТС"."""
import re
import zipfile
import os
import sys
import glob
import logging
import time
import datetime as DT
import xml.etree.ElementTree as ET
from os.path import join, dirname, exists, splitext, basename
import requests
import requests.utils
from dotenv import load_dotenv


def get_exist_file_name(file_dir, file_mask):
    '''Функция проверки наличия файла по маске.'''
    file_path = join(file_dir, file_mask)
    # Получаем список файлов, удовлетворяющих маске
    res0 = glob.glob(file_path)
    # Если список файлов не пустой, 
    # то возвращаем полный путь к первому найденному файлу
    if bool(len(res0) > 0):
        return join(file_dir, res0[0])
    return ""


def convert_path(path: str, ucode: str, region: str, date1) -> str:
    """Конвертируем строку."""
    path = path.replace('%USERCODE%', ucode)
    path = path.replace('%REGION%', region)
    path = path.replace('%YEAR%', date1.strftime('%Y'))
    path = path.replace('%MONTH%', date1.strftime('%m'))
    path = path.replace('%DAY%', date1.strftime('%d'))
    return path


def get_logger() -> logging.Logger:
    '''Инициализация логгера.'''

    _logger = logging.getLogger('py_ats')
    _logger.setLevel(logging.INFO)

    #Если папки с логом нет, то создаем её
    if not exists('LOG'):
        os.makedirs('LOG')
    # создаем handler файла лога
    _fh = logging.FileHandler("LOG/{}_py_ats.log".format(DT.date.today().strftime("%Y-%m-%d")))

    # задаем форматирование
    _formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
    _fh.setFormatter(_formatter)
    # добавляем handler в логгер
    _logger.addHandler(_fh)
    return _logger

start_time = DT.datetime.now()

# Загрузка переменных окружения
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# переменные для искусственной "заморозки" программы. Такая "заморозка" нужна,
# чтобы сайт АТС не снижал искусственно скорость загрузки отчетов
TIME_BETWEEN_TIMEOUT = int(os.environ.get("TIME_BETWEEN_TIMEOUT")) # Интервал времени между "заморозками" программы (в секундах)

TIMEOUT_IN_SECONDS = int(os.environ.get("TIMEOUT_IN_SECONDS")) # Длительность "заморозки" программы

# Определение начальных директорий для настроек и для загрузки отчетов
HOME_DIR_FOR_SAVE = os.environ.get("HOME_DIR_FOR_SAVE")

# Создаем логгер
logger = get_logger()

FIRST_URL = "http://www.atsenergo.ru/auth" # первоначальный URL (без шифрования)
AUTH_URL = "https://www.atsenergo.ru/auth" # URL с шифрованием
REPORT_URL = "https://www.atsenergo.ru/nreport"

# Загрузка параметров командной строки
script_settings = {}
for arg in sys.argv:
    if arg.find('=') != -1:
        script_settings[arg.split('=')[0]] = arg.split('=')[1]

if 'overwrite' not in script_settings.keys():
    script_settings['overwrite'] = 'false'

if 'load_type' not in script_settings.keys():
    script_settings['load_type'] = 'private'

# Определение интервала дат для загрузки
dt_today = DT.date.today()
if 'dt' in script_settings.keys(): # если задана дата dt в параметрах командной строки
    dt1 = DT.datetime.strptime(script_settings['dt'], '%Y%m%d').date()
    if dt1 > dt_today + DT.timedelta(days=1):
        print("Параметр dt не может быть больше завтрашнего дня!")
        sys.exit()
    dt2 = dt1

if 'dt1' in script_settings.keys():
    if script_settings['dt1'][0] == '-':
        TIMESHIFT = int(script_settings['dt1'])
    else:
        TIMESHIFT = 0
        dt1 = DT.datetime.strptime(script_settings['dt1'], '%Y%m%d').date()
    if TIMESHIFT == 0:
        if dt1 > dt_today + DT.timedelta(days=1):
            print("Параметр dt1 не может быть больше завтрашнего дня!")
            sys.exit()

    if 'dt2' not in script_settings.keys():
        dt2 = DT.date.today()
    else:
        dt2 = DT.datetime.strptime(script_settings['dt2'], '%Y%m%d').date()
        if dt2 > dt_today + DT.timedelta(days=1):
            print("Параметр dt2 не может быть больше завтрашнего дня!")
            sys.exit()
        if TIMESHIFT == 0:
            if dt1 > dt2:
                print("Параметр dt1 не может быть больше dt2!")
                sys.exit()
    if TIMESHIFT != 0:
        dt1 = dt2 + DT.timedelta(days=TIMESHIFT)

if 'dt' not in script_settings.keys() and 'dt1' not in script_settings.keys() \
                                and 'dt2' not in script_settings.keys():
    dt2 = DT.date.today()
    dt1 = dt2 + DT.timedelta(days=-65)


# читаем настройки участников ОРЭМ
user_settings = []
if exists('ParticipantSettings.xml'):
    root = ET.parse('ParticipantSettings.xml').getroot()
    for part_tag in root.findall('participant'):
        curr_setting = {'user_name': part_tag.get('userName'),
                        'user_code': part_tag.get('userCode'),
                        'password': part_tag.get('password'),
                        'is_need_to_load': part_tag.get('isNeedToLoad'),
                        'zone': part_tag.get('zone')}
        user_settings.append(curr_setting)

logger.info("------------Start download------------")
time1 = time.time()
# Цикл по участникам
for u_setting in user_settings:
    # проверяем, заданы ли коды участника
    if 'partcode' in script_settings.keys():
        if str(script_settings['partcode']).upper(). \
                find(str(u_setting['user_code']).upper()) == -1:
            continue

    # читаем настройки отчетов (персональных и публичных)
    report_settings = []
    if script_settings['load_type'] == 'public':
        REPORT_SETTINGS_FILE = "ReportSettingsPubl.xml"
    else:
        REPORT_SETTINGS_FILE = "ReportSettingsPart.xml"

    if exists(REPORT_SETTINGS_FILE):
        root = ET.parse(REPORT_SETTINGS_FILE).getroot()
        for rep_tag in root.findall('report'):
            curr_setting = {'name': rep_tag.get('name'),
                            'code': rep_tag.get('code'),
                            'code2': rep_tag.get('code2'),
                            'type': rep_tag.get('type'),
                            'file_mask': rep_tag.get('fileMask'),
                            'load_file_type': rep_tag.get('loadFileType'),
                            'is_need_to_unpack': rep_tag.get('unpack'),
                            'is_need_to_load': rep_tag.get('needToLoad'),
                            'zone': rep_tag.get('region'),
                            'path': rep_tag.get('path')}
            if rep_tag.get('period') is None:
                curr_setting['period'] = 'day'
            else:
                curr_setting['period'] = rep_tag.get('period')
            report_settings.append(curr_setting)

    # Нам нужно создать сессию, чтобы сохранить все куки, получаемые от сайта
    s = requests.Session()

    # Заходим на сайт АТС, чтобы получить куки
    try:
        response = s.get(FIRST_URL, allow_redirects=True)
    except requests.exceptions.RequestException as exception:
        logger.exception(exception)

    # здесь мы делаем POST-запрос на авторизацию
    print("-----------------------------------------------------")
    print("Авторизация пользователя {}".format(u_setting['user_name']))

    postData = {'partcode': u_setting['user_code'],
                'username': u_setting['user_name'],
                'password': u_setting['password'],
                'op': 'Войти'}

    myHeader = {}
    myHeader['Accept'] = "text/html, */*; q=0.01"
    myHeader['Accept-Encoding'] = "gzip, deflate, br"
    myHeader['Accept-Language'] = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    myHeader['Connection'] = 'keep-alive'
    myHeader['Content-Length'] = '101'
    myHeader['Content-Type'] = "application/x-www-form-urlencoded"
    myHeader['Host'] = "www.atsenergo.ru"

    myHeader['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " + \
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/" + \
        "61.0.3163.100 Safari/537.36"
    myHeader['X-Requested-With'] = 'XMLHttpRequest'

    try:
        # вот здесь мы добавляем куки к уже имеющимся
        response = s.post(AUTH_URL, data=postData, headers=myHeader,
                          allow_redirects=True)
        if response.status_code == 200:
            logger.info("Authorization for user %s successful", u_setting['user_code'])
        else:
            logger.error("Authorization for user %s failed. Response status code %s",
                         u_setting['user_code'], response.status_code)
    except requests.exceptions.RequestException as exception:
        logger.exception(exception)

    # Цикл по отчетам
    for report_setting in report_settings:
        # проверяем, заданы ли коды участника
        if 'reportcode' in script_settings.keys():
            if not str(report_setting['code']).lower() in \
                    script_settings['reportcode'].lower().split(','):
                continue

        if report_setting['is_need_to_load'] == 'false':
            continue
        print("Загрузка отчета {}".format(report_setting['name']))
        logger.info("Loading report %s", report_setting['code'])

        # Цикл по ценовым зонам
        if report_setting['zone'] == 'zone':
            ZONE_SETTING = str(u_setting['zone'])
        else:
            ZONE_SETTING = str(report_setting['zone'])
        for zone in ZONE_SETTING.split(';'):
            # Цикл по датам
            dt = dt1
            while dt <= dt2:
                time2 = time.time()
                if time2 - time1 > TIME_BETWEEN_TIMEOUT:
                    time1 = time2
                    print("Ожидание {} секунды...".format(TIMEOUT_IN_SECONDS))
                    time.sleep(TIMEOUT_IN_SECONDS)

                DEST_DIR = join(HOME_DIR_FOR_SAVE,
                                str(report_setting['path']))
                DEST_DIR = convert_path(DEST_DIR, str(u_setting['user_code']),
                                        zone, dt)

                if report_setting['period'] == 'month' and dt.day != 1:
                    dt = dt + DT.timedelta(days=1)
                    continue
                if report_setting['period'] == 'end_of_month' and \
                        (dt + DT.timedelta(days=1)).day != 1:
                    dt = dt + DT.timedelta(days=1)
                    continue

                print(dt)

                # Если целевой папки нет, но создаем её
                if not exists(DEST_DIR):
                    os.makedirs(DEST_DIR)

                PERS_URL = "https://www.atsenergo.ru/nreports?access={}" \
                           .format(report_setting['type'])

                CURR_REPORT_URL = REPORT_URL \
                    + "?rname={}&rdate={}&region={}". \
                    format(report_setting['code'],
                           dt.strftime('%Y%m%d'), zone)
                try:
                    response = s.get(CURR_REPORT_URL)
                    if response.status_code != 200:
                        logger.error("Bad response with code %s", response.status_code)
                except requests.exceptions.RequestException as exception:
                    logger.exception(exception)

                RE_EXPR = r"href=\"\?(fid=[\w&;=]*?)\">([\w.-]*?)<"
                results = re.findall(RE_EXPR, response.text)

                if results is not None:
                    for res in results:
                        base = splitext(res[1])[0]
                        exist_file_name = \
                            get_exist_file_name(DEST_DIR, base + '.*')
                        if exist_file_name != "" and \
                           script_settings['overwrite'].lower() == 'false':
                            pass
                        else:
                            if exist_file_name != "" and \
                              script_settings['overwrite'].lower() == 'true':
                                os.remove(exist_file_name)

                            FILE_URL = ''.join((REPORT_URL, '?', res[0]))
                            if report_setting['load_file_type'] == 'zip':
                                FILE_URL += '&zip=1'

                            try:
                                response = s.get(FILE_URL)
                                if response.status_code != 200:
                                    logger.error("Bad response with loading file %s. \
                                                  Response code %s", \
                                                  basename(exist_file_name), \
                                                  response.status_code)
                            except requests.exceptions.RequestException as exception:
                                logger.exception(exception)

                            FILE_NAME = response.headers['Content-Disposition']. \
                                split('filename=')[1]
                            print("Файл: {}".format(FILE_NAME))
                            logger.info("Loading file: %s", FILE_NAME)

                            FILE_NAME = join(DEST_DIR, FILE_NAME)
                            try:
                                with open(FILE_NAME, 'wb') as report_file:
                                    report_file.write(response.content)
                            except IOError as exception:
                                logger.error("Error with saving file %s", FILE_NAME)

                            if report_setting['is_need_to_unpack'] == 'true':
                                try:
                                    with zipfile.ZipFile(FILE_NAME) as z:
                                        z.extractall(DEST_DIR)
                                    os.remove(FILE_NAME)
                                except zipfile.BadZipFile:
                                    logger.error("Bad zip file. Error with unpacking %s", \
                                                 basename(FILE_NAME))
                                    print("Invalid file {}".format(FILE_NAME))
                                except IOError:
                                    logger.error("IOError with inpacking file %s", FILE_NAME)
                                except:
                                    logger.error("Unknown error with inpacking file %s", FILE_NAME)

                            time2 = time.time()
                            if time2 - time1 > TIME_BETWEEN_TIMEOUT:
                                time1 = time2
                                print("Ожидание {} секунды...".format(TIMEOUT_IN_SECONDS))
                                time.sleep(TIMEOUT_IN_SECONDS)

                dt = dt + DT.timedelta(days=1)
logger.info("Download complete. Script execution time: %s", DT.datetime.now() - start_time)
