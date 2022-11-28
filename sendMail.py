import getpass
import logging
import os.path
import smtplib
from email.message import EmailMessage

import keyring

from exceptions import EmailError


def get_user_password():
    """Получение пароля пользователя."""
    user = getpass.getuser()
    password = keyring.get_password('py_ats', user)
    return user, password


def send_mail(receivers, rep_info, logger: logging.Logger):
    """Отправка почтового сообщения."""
    msg = EmailMessage()
    msg['Subject'] = 'py_ats: Отчеты АТС'
    domain = os.environ.get("DOMAIN")
    smtp_server = os.environ.get("SMTP_SERVER")

    user_name, password = get_user_password()
    from_email = user_name + '@' + domain
    mail_list = receivers.split(';')

    msg['From'] = from_email
    msg['To'] = ', '.join(mail_list)
    msg.set_content("py_ats")

    row_template = """\
    <tr>
        <td>{part_code}</td>
        <td>{report_name}</td>
        <td>
            <a href="{rep_path}">Папка</a>
        </td>
    </tr>
    """

    message_text_teplate = """\
    <html>
    <head></head>
    <body>
        <p>Загружены новые отчеты:</p>
        <table border="1" cellpadding="3">
        {rows}
        </table>
    </body>
    </html>
    """

    rows = ''
    for rep in rep_info:
        rows = rows + row_template.format(**rep)
    message_text = message_text_teplate.format(rows=rows)

    msg.add_alternative(message_text, subtype='html')

    try:
        with smtplib.SMTP(smtp_server, 25) as server:
            server.login(from_email, password)
            server.send_message(msg)
            print("Successfully sent email")
    except Exception as exeption:
        logger.exception(f'Error sending email: {exeption}')
        raise EmailError(f'Error sending email: {exeption}')
    else:
        logger.info('Email successfully sent')
