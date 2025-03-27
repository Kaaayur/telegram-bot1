# Вариант 1: Простой импорт всех модулей
from . import main
from . import config
from . import google_sheets

# Вариант 2: Более явный импорт с указанием, что именно экспортируется
__all__ = [
    'main',
    'config', 
    'google_sheets'
]

# Дополнительно можно добавить версию пакета
__version__ = '1.0.0'
