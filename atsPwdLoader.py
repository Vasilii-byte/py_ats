import getpass
import re
from http import HTTPStatus
from os.path import join
from typing import Dict

import keyring
import requests

from exceptions import (AtsSiteError, DownloadFileError, LogError,
                        PartPasswordNotDefinedError, SavingFileError)


def get_header():
    """Формирование хэдера запроса."""
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


class AtsPwdLoader():
    def __init__(self, logger, verify_status):
        self.part_code = None
        self.user_name = None
        self.password = None
        self.logger = logger
        self.session = None
        self.ATS_URL = 'www.atsenergo.ru'
        self.REPORT_URL = f'https://{self.ATS_URL}/nreport'
        self.verify_status = verify_status

    def save_participant_password(self, part_code: str) -> None:
        """Установка пароля участника ОРЭМ в keyring."""
        password = getpass.getpass(
                prompt=f'Введите пароль для участника {part_code}:'
            )
        keyring.set_password('py_ats', part_code, password)

    def set_participant_password(self) -> None:
        """Получение пароля участника ОРЭМ из keyring."""
        try:
            self.password = keyring.get_password('py_ats', self.part_code)
        except Exception:
            message = f'Не задан пароль для участника ОРЭМ {self.part_code}'
            raise PartPasswordNotDefinedError(message)

    def login(self):
        """Авторизация на сайте."""
        # Нам нужно создать сессию, чтобы сохранить все куки,
        # получаемые от сайта
        auth_url_without_ssl = f'http://{self.ATS_URL}/auth'
        auth_url_with_ssl = f'https://{self.ATS_URL}/auth'
        self.session = requests.Session()

        self.set_participant_password()
        # Заходим на сайт АТС, чтобы получить куки
        try:
            response = self.session.get(
                auth_url_without_ssl,
                allow_redirects=True,
                verify=self.verify_status
            )
        except requests.exceptions.RequestException as exception:
            message = (
                f'Error loading page: {auth_url_without_ssl}. '
                f'Response code {response.status_code} {exception}'
            )
            raise AtsSiteError(message)
        if response.status_code != HTTPStatus.OK:
            message = (
                f'Bad response code for loading page: {auth_url_without_ssl}. '
                f'Error loading page: {auth_url_without_ssl}. '
                f'Response code {response.status_code}'
            )
            raise AtsSiteError(message)

        # здесь мы делаем POST-запрос на авторизацию
        print('-----------------------------------------------------')
        print(f'Авторизация пользователя {self.user_name}')

        post_data = {
            'partcode': self.part_code,
            'username': self.user_name,
            'password': self.password,
            'op': 'Войти'
        }

        my_header = get_header()

        try:
            # вот здесь мы добавляем куки к уже имеющимся
            response = self.session.post(
                auth_url_with_ssl,
                data=post_data,
                headers=my_header,
                allow_redirects=True,
                verify=self.verify_status
            )
        except requests.exceptions.RequestException as exception:
            message = (
                f'Unsuccessful authorization for participant {self.part_code}.'
                f' Response code {response.status_code} {exception}'
            )
            raise LogError(message)
        else:
            if response.status_code == HTTPStatus.OK:
                self.logger.info(
                    ('Authorization for participant '
                     f'{self.part_code} successful')
                )
            else:
                message = (
                    'Bad response code for authorization. '
                    'Unsuccessful authorization for '
                    f'participant {self.part_code}. '
                    f'Response code {response.status_code}'
                )
                raise LogError(message)

    def init_session(self):
        """Создание сессии."""
        # Нам нужно создать сессию, чтобы сохранить все куки,
        # получаемые от сайта
        url_with_ssl = 'https://www.atsenergo.ru/results/rsv'
        self.session = requests.Session()

        # Заходим на сайт АТС, чтобы получить куки
        try:
            response = self.session.get(
                url_with_ssl,
                allow_redirects=True,
                verify=self.verify_status
            )
        except requests.exceptions.RequestException as exception:
            message = (
                f'Error loading page: {url_with_ssl}. '
                f'Repponse code {response.status_code} {exception}'
            )
            raise AtsSiteError(message)
        if response.status_code != HTTPStatus.OK:
            message = (
                f'Error loading page: {url_with_ssl}. '
                f'Response code {response.status_code}'
            )
            raise AtsSiteError(message)

    def load_report_url(self, zone: str,
                        report_code: str,
                        report_date: str) -> requests.Response:
        """Загрузка страницы отчета."""
        params = {
            'rname': report_code,
            'rdate': report_date,
            'region': zone
        }
        try:
            response = self.session.get(
                self.REPORT_URL,
                params=params,
                verify=self.verify_status
            )
        except requests.exceptions.RequestException as exception:
            message = (
                f'Error loading page: {self.REPORT_URL}. '
                f'Response code {response.status_code} {exception}'
            )
            raise AtsSiteError(message)
        if response.status_code != HTTPStatus.OK:
            message = (
                f'Error loading page: {self.REPORT_URL}. '
                f'Response code {response.status_code}'
            )
            raise AtsSiteError(message)
        else:
            return response

    def get_report_files_from_url(self, response: requests.Response) -> Dict:
        """Получение списка файлов для загрузки со страницы отчета."""
        report_files = {}
        re_expr = r'href=\"\?(fid=[\w&;=]*?)\">([\w.-]*?)<'
        results = re.findall(re_expr, response.text)

        if results is not None:
            for res in results:
                fid = res[0]
                report_files[fid] = res[1]
        return report_files

    def download_file(self, fid, zip, report_file, dest_dir):
        """Загрузка файла отчета и его сохранение на диск."""
        file_url = ''.join((self.REPORT_URL, '?', fid))
        if zip:
            file_url += '&zip=1'
        try:
            response = self.session.get(file_url, verify=self.verify_status)
        except requests.exceptions.RequestException as exception:
            message = (f'Bad response with '
                       f'loading file {report_file}. '
                       f'Response code {response.status_code}: {exception}')
            raise DownloadFileError(message)
        if response.status_code != HTTPStatus.OK:
            message = (f'Bad response with '
                       f'loading file {report_file}. '
                       f'Response code {response.status_code}')
            raise DownloadFileError(message)

        file_name = response.headers['Content-Disposition'].\
            split('filename=')[1]
        print(f'Файл: {file_name}')
        self.logger.info(f'Download file: {file_name}')

        file_name = join(dest_dir, file_name)
        try:
            with open(file_name, 'wb') as report_file:
                report_file.write(response.content)
        except IOError as exception:
            raise SavingFileError(
                f'Error saving file {file_name}: {exception}'
            )
        else:
            return file_name
