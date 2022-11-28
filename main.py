#!/usr/bin/env python
# coding: utf-8

"""Скрипт по загрузке данных с сайта АО "АТС"."""
import datetime
import getpass
import glob
import logging
import os
import sys
import time
import xml.etree.ElementTree as ElementTree
import zipfile
from logging.handlers import RotatingFileHandler
from os.path import basename, dirname, exists, join, splitext
from typing import List

import keyring
import urllib3
from dotenv import load_dotenv
from lxml import etree

from atsCryptoLoader import AtsCryptoLoader
from atsPwdLoader import AtsPwdLoader
from sendMail import send_mail


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
    _fh = RotatingFileHandler('LOG/py_ats.log',
                              maxBytes=10000000, backupCount=5)

    # задаем форматирование
    _formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
    _fh.setFormatter(_formatter)
    # добавляем handler в логгер
    _logger.addHandler(_fh)
    return _logger


def set_user_password():
    """Установка пароля пользователя."""
    user = getpass.getuser()
    password = getpass.getpass(
        prompt=f'Введите пароль для пользователя {user}:'
    )
    keyring.set_password('py_ats', user, password)
    return


def get_user_password():
    """Получение пароля пользователя."""
    user = getpass.getuser()
    password_dict = {}
    password_dict[user] = keyring.get_password('py_ats', user)
    return password_dict


def set_participant_passwords(part_code):
    """Установка пароля участника ОРЭМ."""
    password = getpass.getpass(
            prompt=f'Введите пароль для участника {part_code}:'
        )
    keyring.set_password('py_ats', part_code, password)


def get_participant_password(part_code):
    """Получение пароля участника ОРЭМ."""
    return keyring.get_password('py_ats', part_code)


def get_dates(scr_settings, max_timeshift):
    """Определение интервала дат для загрузки."""

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
        dt1 = dt2 + datetime.timedelta(days=max_timeshift)
    return dt1, dt2


def get_participant_settings(reportcode_args: str, load_type: str) -> List:
    """Чтение настроек участников ОРЭМ."""
    if reportcode_args == '':
        participants_to_load = ['-']
    else:
        participants_to_load = reportcode_args.upper().split(',')

    part_settings = []
    if load_type == 'public':
        curr_setting = {'user_name': '',
                        'user_code': '',
                        'is_need_to_load': True,
                        'zone': 'eur;sib'}
        part_settings.append(curr_setting)
    else:
        if exists('ParticipantSettings.xml'):
            root = ElementTree.parse('ParticipantSettings.xml').getroot()
            for part_tag in root.findall('participant'):
                part_code = part_tag.get('userCode')
                user_emails = part_tag.get('userEmails')
                is_need_to_load = (part_tag.get('isNeedToLoad').upper()
                                   == 'TRUE')

                if ((part_code in participants_to_load and
                     is_need_to_load is True)
                        or (participants_to_load == ['-'] and is_need_to_load is True)):
                    curr_setting = {'user_name': part_tag.get('userName'),
                                    'user_code': part_code,
                                    'is_need_to_load': is_need_to_load,
                                    'user_emails': user_emails,
                                    'zone': part_tag.get('zone')}
                    part_settings.append(curr_setting)
    return part_settings


def unpack_archive(dest_dir, file_name, logger):
    """Распаковка архива в нужную директорию."""
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
    except Exception as err:
        logger.error(f"Unknown error with inpacking file {file_name}: {err}")


def load_from_main_source(script_settings):
    start_time = datetime.datetime.now()

    # Загрузка переменных окружения
    dotenv_path = join(dirname(__file__), '.env')
    load_dotenv(dotenv_path)

    # переменные для искусственной "заморозки" программы. Такая "заморозка"
    # нужна, чтобы сайт АТС не снижал искусственно скорость загрузки отчетов
    # Интервал времени между "заморозками" программы (в секундах)
    TIME_BETWEEN_TIMEOUT = int(os.environ.get("TIME_BETWEEN_TIMEOUT"))      # noqa

    VERIFY_STATUS = int(os.environ.get("VERIFY_STATUS")) == 1     # noqa

    # Длительность "заморозки" программы
    TIMEOUT_IN_SEC = int(os.environ.get("TIMEOUT_IN_SECONDS"))              # noqa

    # Определение начальных директорий для настроек и для загрузки отчетов
    HOME_DIR_FOR_SAVE = os.environ.get("HOME_DIR_FOR_SAVE")                 # noqa

    REPORT_SETTINGS_PUB_FILE = os.environ.get("REPORT_SETTINGS_PUB_FILE")   # noqa
    REPORT_SETTINGS_PRIV_FILE = os.environ.get("REPORT_SETTINGS_PRIV_FILE") # noqa

    MAX_TIMESHIFT = int(os.environ.get("MAX_TIMESHIFT"))                    # noqa

    # Создаем логгер
    logger = get_logger()

    if 'overwrite' not in script_settings.keys():
        script_settings['overwrite'] = 'false'

    if 'load_type' not in script_settings.keys():
        script_settings['load_type'] = 'private'

    dt1, dt2 = get_dates(script_settings, MAX_TIMESHIFT)

    # получаем список настроек участников ОРЭМ
    if 'partcode' not in script_settings:
        participants = get_participant_settings(
            '',
            script_settings['load_type']
        )
    else:
        participants = get_participant_settings(
            script_settings['partcode'],
            script_settings['load_type']
        )

    # user_settings = get_user_settings()

    logger.info("------------Start download------------")
    time1 = time.time()
    # Цикл по участникам

    emails_by_receivers = {}
    for participant in participants:
        # Создаем список получателей и писем для них
        if script_settings['load_type'] == 'private':
            email = participant['user_emails']
            emails_by_receivers[email] = []

    for participant in participants:
        part_code = str(participant['user_code']).upper()

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
                                'notify': rep_tag.get('notify', 'False'),
                                'code2': rep_tag.get('code2'),
                                'type': rep_tag.get('type'),
                                'file_mask': rep_tag.get('fileMask'),
                                'load_file_type': rep_tag.get('loadFileType'),
                                'is_need_to_unpack': rep_tag.get('unpack'),
                                'is_need_to_load': rep_tag.get('needToLoad', 'true'),
                                'zone': rep_tag.get('region'),
                                'path': rep_tag.get('path')}
                if rep_tag.get('period') is None:
                    curr_setting['period'] = 'day'
                else:
                    curr_setting['period'] = rep_tag.get('period')
                report_settings.append(curr_setting)

        try:
            loader = AtsPwdLoader(logger=logger, verify_status=VERIFY_STATUS)
            loader.part_code = part_code
            loader.user_name = participant['user_name']

            if script_settings['load_type'] == 'private':
                loader.login()
            else:
                loader.init_session()

            # Цикл по отчетам
            for report in report_settings:
                # проверяем, заданы ли коды участника
                if 'reportcode' in script_settings.keys():
                    if (not str(report['code']).lower()
                            in script_settings['reportcode'].lower().split(',')):
                        continue

                if report['is_need_to_load'] == 'false':
                    continue
                print(f"Загрузка отчета {report['name']}")

                # Цикл по ценовым зонам
                if report['zone'] == 'zone':
                    price_zones = str(participant['zone'])
                else:
                    price_zones = str(report['zone'])

                for zone in price_zones.split(';'):
                    # Цикл по датам
                    files_count = 0
                    dt = dt1
                    while dt <= dt2:
                        time2 = time.time()
                        if time2 - time1 > TIME_BETWEEN_TIMEOUT:
                            time1 = time2
                            print(f"Ожидание {TIMEOUT_IN_SEC} секунды...")
                            time.sleep(TIMEOUT_IN_SEC)

                        dest_dir = convert_path(
                            join(HOME_DIR_FOR_SAVE, str(report['path'])),
                            str(loader.part_code),
                            zone,
                            dt
                        )

                        if report['period'] == 'month' and dt.day != 1:
                            dt = dt + datetime.timedelta(days=1)
                            continue
                        if (report['period'] == 'end_of_month'
                                and (dt + datetime.timedelta(days=1)).day != 1):
                            dt = dt + datetime.timedelta(days=1)
                            continue

                        print(dt)

                        # Если целевой папки нет, но создаем её
                        if not exists(dest_dir):
                            os.makedirs(dest_dir)

                        # загрузка страницы отчета
                        response = loader.load_report_url(
                            zone=zone,
                            report_code=report['code'],
                            report_date=dt.strftime('%Y%m%d')
                        )

                        report_files = loader.get_report_files_from_url(response)

                        for fid, report_file in report_files.items():
                            base_name = splitext(report_file)[0]
                            exist_file_name = get_exist_file_name(
                                dest_dir,
                                base_name + '.*'
                            )
                            if (exist_file_name != ""
                                    and script_settings['overwrite'].lower()
                                    == 'false'):
                                pass
                            else:
                                if (exist_file_name != "" and
                                        script_settings['overwrite'].lower()
                                        == 'true'):
                                    os.remove(exist_file_name)

                                if report['load_file_type'] == 'zip':
                                    zip_report = True
                                else:
                                    zip_report = False

                                # Загрузка файла отчета
                                file_name = loader.download_file(
                                    fid,
                                    zip=zip_report,
                                    report_file=report_file,
                                    dest_dir=dest_dir
                                )

                                if report['is_need_to_unpack'].lower() == 'true':
                                    unpack_archive(dest_dir, file_name, logger)
                                files_count = files_count + 1

                                time2 = time.time()
                                if time2 - time1 > TIME_BETWEEN_TIMEOUT:
                                    time1 = time2
                                    print(
                                        f'Ожидание {TIMEOUT_IN_SEC} секунды...'
                                    )
                                    time.sleep(TIMEOUT_IN_SEC)
                        # for fid, report_file in report_files.items():

                        dt = dt + datetime.timedelta(days=1)
                    # while dt <= dt2:
                    if report['notify'].upper() == 'TRUE' and files_count > 0:
                        row_to_send = {
                            'part_code': part_code,
                            'report_name': report['name'],
                            'rep_path': dest_dir
                        }
                        email = participant['user_emails']
                        emails_by_receivers[email].append(row_to_send)
                # for zone in ZONE_SETTING.split(';'):
            # for report_setting in report_settings:
        except Exception as err:
            logger.exception(err)
            print(err)
            raise Exception(err)
    logger.info(
        "Download complete. Script execution time: %s",
        datetime.datetime.now() - start_time
    )
    for email, reports in emails_by_receivers.items():
        if len(reports) > 0:
            send_mail(email, reports, logger)


def load_from_crypto_source(script_settings):
    # start_time = datetime.datetime.now()

    # Загрузка переменных окружения
    dotenv_path = join(dirname(__file__), '.env')
    load_dotenv(dotenv_path)

    # переменные для искусственной "заморозки" программы. Такая "заморозка"
    # нужна, чтобы сайт АТС не снижал искусственно скорость загрузки отчетов
    # Интервал времени между "заморозками" программы (в секундах)
    TIME_BETWEEN_TIMEOUT = int(os.environ.get("TIME_BETWEEN_TIMEOUT"))      # noqa

    VERIFY_STATUS = int(os.environ.get("VERIFY_STATUS")) == 1     # noqa

    # Длительность "заморозки" программы
    TIMEOUT_IN_SEC = int(os.environ.get("TIMEOUT_IN_SECONDS"))              # noqa

    # Определение начальных директорий для настроек и для загрузки отчетов
    HOME_DIR_FOR_SAVE = os.environ.get("HOME_DIR_FOR_SAVE")                 # noqa

    REPORT_SETTINGS_PUB_FILE = os.environ.get("REPORT_SETTINGS_PUB_FILE")   # noqa
    REPORT_SETTINGS_PRIV_FILE = os.environ.get("REPORT_SETTINGS_PRIV_FILE") # noqa

    MAX_TIMESHIFT = int(os.environ.get("MAX_TIMESHIFT"))                    # noqa

    # Создаем логгер
    logger = get_logger()

    if 'overwrite' not in script_settings.keys():
        script_settings['overwrite'] = 'false'

    dt1, dt2 = get_dates(script_settings, MAX_TIMESHIFT)

    # получаем список настроек участников ОРЭМ
    logger.info("------------Start download------------")
    # time1 = time.time()
    # Цикл по участникам

    loader = AtsCryptoLoader(logger=logger, verify_status=VERIFY_STATUS)
    loader.get_cert_from_json()
    loader.part_code = 'MOSENERG'
    res = loader.login()
    loader.read_reports_to_dict(res)
    for rep_name, url in loader.rep_dict.items():
        print(rep_name)
        print('https://' + loader.ATS_URL + url)
        html = loader.get_page('https://' + loader.ATS_URL + url)

        table = etree.HTML(html).find("body/table")
        rows = iter(table)
        headers = [col.text for col in next(rows)]
        for row in rows:
            values = [col.text for col in row]
            print(dict(zip(headers, values)))
        if rep_name == 'Документы по РД':
            return


def main():
    urllib3.disable_warnings()

    # Сохранение пароля для пользователя
    script_settings = {}
    if '--user-pass' in sys.argv:
        set_user_password()
        print('Пароль записан')
        sys.exit(0)

    # Сохранение пароля для участника ОРЭМ
    for arg in sys.argv:
        if arg.startswith('--participant-pass'):
            part_code = arg.split('=')[1]
            set_participant_passwords(part_code)
            print('Пароль записан')
            sys.exit(0)

    for arg in sys.argv:
        if arg.find('=') != -1:
            script_settings[arg.split('=')[0]] = arg.split('=')[1]

    if script_settings['source_type'] == 'ats_reports':
        load_from_main_source(script_settings)
    if script_settings['source_type'] == 'crypto':
        load_from_crypto_source(script_settings)


if __name__ == '__main__':
    main()
