import os

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
GROUP_CHAT_ID = int(os.environ['GROUP_CHAT_ID'])
GOOGLE_CREDENTIALS_FILE = os.environ['GOOGLE_CREDENTIALS_FILE']
SPREADSHEET_KEY = '1o7jeq7iE9H0kYY4Xl-x51dRWqLOudmHqGXY_i-m-kZI'

ANIMATOR_IDS = {
    "413165965": "Настя",
    "283779327": "Егор",
    # ...
}

KEYWORDS = ["в пути", "на месте", "закончил"]

#  Для PythonAnywhere:
PA_USERNAME = os.environ['PA_USERNAME']  #  Ваше имя пользователя на PythonAnywhere
