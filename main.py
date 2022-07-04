#!/usr/bin/env python
# coding: utf-8

"""Скрипт по загрузке данных с сайта АО "АТС"."""
import datetime
import getpass
import glob
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ElementTree
import zipfile
from http import HTTPStatus
from os.path import basename, dirname, exists, join, splitext

import keyring
import requests
import requests.utils
import urllib3
from dotenv import load_dotenv


def get_header():
    """Формирование хедера запроса."""
    my_header = {}
    my_header['Accept'] = 'text/html, */*; q=0.01'
    my_header['Accept-Encoding'] = 'gzip, deflate, br'
    my_header['Accept-Language'] = 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
    my_header['Connection'] = 'keep-alive'
    my_header['Content-Length'] = '101'
    my_header['Content-Type'] = 'application/x-www-form-urlencoded'
    my_header['Host'] = 'www.atsenergo.ru'

    my_header['User-Agent'] = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/'
                               '61.0.3163.100 Safari/537.36')
    my_header['X-Requested-With'] = 'XMLHttpRequest'
    return my_header


def get_exist_file_name(file_dir: str, file_mask: str) -> str:
    """Функция проверки наличия файла в папке по маске."""
    file_path = join(file_dir, file_mask)
    # Получаем список файлов, удовлетворяющих маске
    res0 = glob.glob(file_path)
    # Если список файлов не пустой,
    # то возвращаем полный путь к первому найденному файлу
    if bool(len(res0) > 0):
        return join(file_dir, res0[0])
    return ''


def convert_path(path: str, ucode: str, region: str, date1) -> str:
    """Конвертируем строку."""
    replace_masks = {
        '%USERCODE%': ucode,
        '%REGION%': region,
        '%YEAR%': date1.strftime('%Y'),
        '%MONTH%': date1.strftime('%m'),
        '%DAY%': date1.strftime('%d')
    }
    for old_str, new_str in replace_masks.items():
        path = path.replace(old_str, new_str)
    return path


def get_logger() -> logging.Logger:
    """Инициализация логгера."""

    _logger = logging.getLogger('py_ats')
    _logger.setLevel(logging.INFO)

    # Если папки с логом нет, то создаем её
    if not exists('LOG'):
        os.makedirs('LOG')
    # создаем handler файла лога
    _date_in_filename = datetime.date.today().strftime("%Y-%m-%d")
    _fh = logging.FileHandler(f'LOG/{_date_in_filename}_py_ats.log')

    # задаем форматирование
    _formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
    _fh.setFormatter(_formatter)
    # добавляем handler в логгер
    _logger.addHandler(_fh)
    return _logger


def set_user_password():
    user = getpass.getuser()
    password = getpass.getpass(
        prompt=f'Введите пароль для пользователя {user}:'
    )
    return user, password


def get_user_password():
    user = getpass.getuser()
    password_dict = {}
    password_dict[user] = keyring.get_password('py_ats', user)
    return password_dict


def set_participant_passwords(part_code):
    return getpass.getpass(
            prompt=f'Введите пароль для участника {part_code}:'
        )


def get_participant_password(part_code):
    return keyring.get_password('py_ats', part_code)


def get_dates(scr_settings):
    """Определение интервала дат для загрузки."""

    MAX_TIMESHIFT: int = -65
    dt_today = datetime.date.today()
    # если задана дата dt в параметрах командной строки
    if 'dt' in scr_settings.keys():
        dt1 = datetime.datetime.strptime(scr_settings['dt'], '%Y%m%d').date()
        if dt1 > dt_today + datetime.timedelta(days=1):
            print("Параметр dt не может быть больше завтрашнего дня!")
            sys.exit()
        dt2 = dt1

    if 'dt1' in scr_settings.keys():
        if scr_settings['dt1'][0] == '-':
            timeshift = int(scr_settings['dt1'])
        else:
            timeshift = 0
            dt1 = datetime.datetime.strptime(
                scr_settings['dt1'], '%Y%m%d'
            ).date()
        if timeshift == 0:
            if dt1 > dt_today + datetime.timedelta(days=1):
                print("Параметр dt1 не может быть больше завтрашнего дня!")
                sys.exit()

        if 'dt2' not in scr_settings.keys():
            dt2 = datetime.date.today()
        else:
            dt2 = datetime.datetime.strptime(
                scr_settings['dt2'], '%Y%m%d'
            ).date()
            if dt2 > dt_today + datetime.timedelta(days=1):
                print("Параметр dt2 не может быть больше завтрашнего дня!")
                sys.exit()
            if timeshift == 0:
                if dt1 > dt2:
                    print("Параметр dt1 не может быть больше dt2!")
                    sys.exit()
        if timeshift != 0:
            dt1 = dt2 + datetime.timedelta(days=timeshift)

    if ('dt' not in scr_settings.keys()
            and 'dt1' not in scr_settings.keys()
            and 'dt2' not in scr_settings.keys()):
        dt2 = datetime.date.today()
        dt1 = dt2 + datetime.timedelta(days=MAX_TIMESHIFT)
    return dt1, dt2


def get_user_settings():
    '''Читаем настройки участников ОРЭМ.'''
    user_settings = []
    if exists('ParticipantSettings.xml'):
        root = ElementTree.parse('ParticipantSettings.xml').getroot()
        for part_tag in root.findall('participant'):
            curr_setting = {'user_name': part_tag.get('userName'),
                            'user_code': part_tag.get('userCode'),
                            # 'password': part_tag.get('password'),
                            'is_need_to_load': part_tag.get('isNeedToLoad'),
                            'zone': part_tag.get('zone')}
            user_settings.append(curr_setting)
    return user_settings


def log_into(user_name, user_code, ats_url, verify_status, logger):
    '''Авторизация на сайте.'''
    # Нам нужно создать сессию, чтобы сохранить все куки,
    # получаемые от сайта
    auth_url_without_ssl = f"http://{ats_url}/auth"
    auth_url_with_ssl = f"https://{ats_url}/auth"
    session = requests.Session()
    result = True

    # Заходим на сайт АТС, чтобы получить куки
    try:
        response = session.get(auth_url_without_ssl, allow_redirects=True,
                               verify=verify_status)
    except requests.exceptions.RequestException as exception:
        logger.exception(exception)
        print(f'Ошибка загрузки страницы {auth_url_without_ssl}')
        return False, session

    # здесь мы делаем POST-запрос на авторизацию
    print("-----------------------------------------------------")
    print(f"Авторизация пользователя {user_name}")

    post_data = {
        'partcode': user_code,
        'username': user_name,
        'password': get_participant_password(user_code),
        'op': 'Войти'
    }

    my_header = get_header()

    try:
        # вот здесь мы добавляем куки к уже имеющимся
        response = session.post(
            auth_url_with_ssl,
            data=post_data,
            headers=my_header,
            allow_redirects=True,
            verify=verify_status
        )
        if response.status_code == HTTPStatus.OK:
            logger.info(f"Authorization for user {user_code} successful")
        else:
            logger.error(
                (
                    f"Authorization for user {user_code} failed. "
                    f"Response status code {response.status_code}"
                )
            )
            result = False
    except requests.exceptions.RequestException as exception:
        logger.exception(exception)
        result = False
    return result, session


def unpack_archive(dest_dir, file_name, logger):
    '''Распаковка архива в нужную директорию.'''
    try:
        with zipfile.ZipFile(file_name) as z:
            z.extractall(dest_dir)
        os.remove(file_name)
    except zipfile.BadZipFile:
        logger.error(
            (f'Bad zip file. Error with unpacking '
             f'{basename(file_name)}')
        )
        print(f'Invalid file {file_name}')
    except IOError:
        logger.error(f"IOError with inpacking file {file_name}")
    except:
        logger.error(f"Unknown error with inpacking file {file_name}")


def main():
    urllib3.disable_warnings()
    VERIFY_STATUS: boolean = False

    start_time = datetime.datetime.now()

    # Загрузка переменных окружения
    dotenv_path = join(dirname(__file__), '.env')
    load_dotenv(dotenv_path)

    # переменные для искусственной "заморозки" программы. Такая "заморозка"
    # нужна, чтобы сайт АТС не снижал искусственно скорость загрузки отчетов
    # Интервал времени между "заморозками" программы (в секундах)
    TIME_BETWEEN_TIMEOUT = int(os.environ.get("TIME_BETWEEN_TIMEOUT"))

    # Длительность "заморозки" программы
    TIMEOUT_IN_SECONDS = int(os.environ.get("TIMEOUT_IN_SECONDS"))

    # Определение начальных директорий для настроек и для загрузки отчетов
    HOME_DIR_FOR_SAVE = os.environ.get("HOME_DIR_FOR_SAVE")

    REPORT_SETTINGS_PUB_FILE = os.environ.get("REPORT_SETTINGS_PUB_FILE")
    REPORT_SETTINGS_PRIV_FILE = os.environ.get("REPORT_SETTINGS_PRIV_FILE")

    # Создаем логгер
    logger = get_logger()

    ATS_URL = 'www.atsenergo.ru'
    # URL с шифрованием
    REPORT_URL = f"https://{ATS_URL}/nreport"

    # Загрузка параметров командной строки
    script_settings = {}
    if '--user-pass' in sys.argv:
        user, password = set_user_password()
        keyring.set_password('py_ats', user, password)
        print('Пароль записан')
        sys.exit(0)

    for arg in sys.argv:
        if arg.startswith('--participant-pass'):
            part_code = arg.split('=')[1]
            password = set_participant_passwords(part_code)
            keyring.set_password('py_ats', part_code, password)
            print('Пароль записан')
            sys.exit(0)

    user_password = get_user_password()
    for arg in sys.argv:

        if arg.find('=') != -1:
            script_settings[arg.split('=')[0]] = arg.split('=')[1]

    if 'overwrite' not in script_settings.keys():
        script_settings['overwrite'] = 'false'

    if 'load_type' not in script_settings.keys():
        script_settings['load_type'] = 'private'

    dt1, dt2 = get_dates(script_settings)

    # читаем настройки участников ОРЭМ
    user_settings = get_user_settings()

    logger.info("------------Start download------------")
    time1 = time.time()
    # Цикл по участникам
    for u_setting in user_settings:
        user_code = str(u_setting['user_code']).upper()

        # проверяем, заданы ли коды участника
        if 'partcode' in script_settings.keys():
            if str(script_settings['partcode']).upper().find(user_code) == -1:
                continue

        # читаем настройки отчетов (персональных и публичных)
        report_settings = []
        if script_settings['load_type'] == 'public':
            report_settings_file = REPORT_SETTINGS_PUB_FILE
        else:
            report_settings_file = REPORT_SETTINGS_PRIV_FILE

        if exists(report_settings_file):
            root = ElementTree.parse(report_settings_file).getroot()
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

        result, session = log_into(u_setting['user_name'], user_code, ATS_URL,
                                   VERIFY_STATUS,
                                   logger)
        if result is False:
            sys.exit(1)

        # Цикл по отчетам
        for report_setting in report_settings:
            # проверяем, заданы ли коды участника
            if 'reportcode' in script_settings.keys():
                if (not str(report_setting['code']).lower()
                        in script_settings['reportcode'].lower().split(',')):
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
                        print(f"Ожидание {TIMEOUT_IN_SECONDS} секунды...")
                        time.sleep(TIMEOUT_IN_SECONDS)

                    dest_dir = convert_path(
                        join(HOME_DIR_FOR_SAVE, str(report_setting['path'])),
                        str(u_setting['user_code']),
                        zone,
                        dt
                    )

                    if report_setting['period'] == 'month' and dt.day != 1:
                        dt = dt + datetime.timedelta(days=1)
                        continue
                    if (report_setting['period'] == 'end_of_month'
                            and (dt + datetime.timedelta(days=1)).day != 1):
                        dt = dt + datetime.timedelta(days=1)
                        continue

                    print(dt)

                    # Если целевой папки нет, но создаем её
                    if not exists(dest_dir):
                        os.makedirs(dest_dir)

                    params = {
                        'rname': report_setting['code'],
                        'rdate': dt.strftime('%Y%m%d'),
                        'region': zone
                    }
                    try:
                        response = session.get(REPORT_URL, params=params,
                                               verify=VERIFY_STATUS)
                        if response.status_code != HTTPStatus.OK:
                            logger.error(
                                "Bad response with code %s",
                                response.status_code
                            )
                    except requests.exceptions.RequestException as exception:
                        logger.exception(exception)

                    RE_EXPR = r"href=\"\?(fid=[\w&;=]*?)\">([\w.-]*?)<"
                    results = re.findall(RE_EXPR, response.text)

                    if results is not None:
                        for res in results:
                            base = splitext(res[1])[0]
                            exist_file_name = \
                                get_exist_file_name(dest_dir, base + '.*')
                            if (exist_file_name != ""
                                    and script_settings['overwrite'].lower()
                                    == 'false'):
                                pass
                            else:
                                if (exist_file_name != "" and
                                        script_settings['overwrite'].lower()
                                        == 'true'):
                                    os.remove(exist_file_name)

                                FILE_URL = ''.join((REPORT_URL, '?', res[0]))
                                if report_setting['load_file_type'] == 'zip':
                                    FILE_URL += '&zip=1'
                                try:
                                    response = session.get(FILE_URL, verify=VERIFY_STATUS)
                                    if response.status_code != HTTPStatus.OK:
                                        logger.error(
                                            (f'Bad response with '
                                             f'loading file {basename(exist_file_name)}. '
                                             f'Response code {response.status_code}')
                                        )
                                except requests.exceptions.RequestException as exception:
                                    logger.exception(exception)

                                file_name = response.headers['Content-Disposition']. \
                                    split('filename=')[1]
                                print("Файл: {}".format(file_name))
                                logger.info("Loading file: %s", file_name)

                                file_name = join(dest_dir, file_name)
                                try:
                                    with open(file_name, 'wb') as report_file:
                                        report_file.write(response.content)
                                except IOError as exception:
                                    logger.error(
                                        f"Error with saving file {file_name}"
                                    )
                                    logger.error(exception)

                                if report_setting['is_need_to_unpack'] == 'true':
                                    unpack_archive(dest_dir, file_name, logger)

                                time2 = time.time()
                                if time2 - time1 > TIME_BETWEEN_TIMEOUT:
                                    time1 = time2
                                    print(
                                        f'Ожидание {TIMEOUT_IN_SECONDS} секунды...'
                                    )
                                    time.sleep(TIMEOUT_IN_SECONDS)

                    dt = dt + datetime.timedelta(days=1)
    logger.info(
        "Download complete. Script execution time: %s",
        datetime.datetime.now() - start_time
    )


if __name__ == '__main__':
    main()
