# /opt/render/project/src/bot/main.py

import os
import logging
import json
from typing import List, Dict, Optional # Добавил Optional
from flask import Flask, request, abort
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import asyncio # Добавил asyncio
from asgiref.wsgi import WsgiToAsgi # <--- ИМПОРТ ДЛЯ ОБЕРТКИ WSGI -> ASGI

# --- НАСТРОЙКА ---
CREDENTIALS_FILE_PATH = "credentials.json"  # Имя файла, который мы создадим

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, # Используй INFO или DEBUG по необходимости
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- СОЗДАНИЕ ФАЙЛА УЧЕТНЫХ ДАННЫХ GOOGLE ПРИ ЗАПУСКЕ ---
# ВАЖНО: Этот код будет выполняться КАЖДЫМ воркером Uvicorn.
# Он попытается перезаписать файл credentials.json.
# Чтение этого файла должно быть устойчивым к гонкам состояний.
GOOGLE_CREDS_AVAILABLE = False # Инициализируем как False
try:
    # Читаем JSON СТРОКУ из переменной окружения
    google_creds_json_str = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON', '{}')
    if not google_creds_json_str or google_creds_json_str == '{}':
        raise ValueError("Переменная окружения GOOGLE_SHEETS_CREDENTIALS_JSON не установлена или пуста!")

    # Пытаемся распарсить JSON, чтобы убедиться, что он валидный
    creds_dict = json.loads(google_creds_json_str)

    # Записываем содержимое в файл credentials.json
    # Это может вызввать проблемы с правами или блокировками, но попробуем
    with open(CREDENTIALS_FILE_PATH, "w") as f:
        json.dump(creds_dict, f)
    logger.info(f"✅ Файл учетных данных {CREDENTIALS_FILE_PATH} создан (может дублироваться воркерами).")
    GOOGLE_CREDS_AVAILABLE = True # Устанавливаем в True, если файл успешно записан этим воркером

except (ValueError, json.JSONDecodeError, FileNotFoundError, OSError) as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при создании {CREDENTIALS_FILE_PATH}: {e}")
    # GOOGLE_CREDS_AVAILABLE останется False


# --- КЛАССЫ КОНФИГУРАЦИИ И МЕНЕДЖЕР GOOGLE SHEETS ---
# Используй свои реальные классы или эти доработанные заглушки

try:
    # Попытка импортировать твои реальные классы
    from bot.config import Config
    from bot.google_sheets import GoogleSheetsManager # Предполагаем, что он доработан для безопасного чтения

except ImportError:
    logger.warning("Не удалось импортировать Config или GoogleSheetsManager из bot.*, используются заглушки.")

    # --- Заглушка Config ---
    class Config:
        BOT_TOKEN = os.getenv('BOT_TOKEN', "YOUR_BOT_TOKEN_HERE") # Получаем из env или используем заглушку
        # GOOGLE_SHEETS_CREDENTIALS_JSON больше не нужен здесь, он читается напрямую из env выше
        GOOGLE_SHEETS_SPREADSHEET_NAME = "АнимельБот" # Имя таблицы
        GOOGLE_SHEETS_WORKSHEET_NAME = "Статусы"     # Имя листа

    # --- Доработанная Заглушка GoogleSheetsManager ---
    class GoogleSheetsManager:
        """
        Заглушка менеджера Google Sheets с безопасной инициализацией,
        устойчивой к гонкам состояний при чтении credentials.json.
        """
        def __init__(self, credentials_path=None):
            self.client = None
            self.spreadsheet = None
            self.worksheet = None
            logger.info(f"Попытка инициализации GoogleSheetsManager с файлом: {credentials_path}")

            if not credentials_path:
                logger.warning("Путь к файлу учетных данных не передан в GoogleSheetsManager.")
                return

            # Проверяем файл перед попыткой чтения (защита от гонки)
            if os.path.exists(credentials_path) and os.path.getsize(credentials_path) > 2: # > 2 чтобы исключить пустой '{}'
                logger.debug(f"Файл {credentials_path} существует и не пуст, попытка инициализации gspread.")
                try:
                    # Имитируем инициализацию клиента (в реальном коде здесь будет gspread)
                    import gspread # Убедись, что gspread установлен и есть в requirements.txt
                    # Оборачиваем вызов gspread в try-except на случай ошибки парсинга
                    try:
                         self.client = gspread.service_account(filename=credentials_path)
                         logger.info("Клиент gspread УСПЕШНО инициализирован.")
                    except json.JSONDecodeError as json_err:
                         # Ошибка парсинга JSON внутри gspread
                         logger.error(f"Ошибка парсинга JSON в gspread при чтении {credentials_path}: {json_err}")
                    except Exception as gspread_err:
                         # Другая ошибка gspread
                         logger.error(f"Неожиданная ошибка gspread.service_account: {gspread_err}")

                except ImportError:
                    logger.error("ЗАГЛУШКА: Библиотека gspread не найдена. Установите ее (`pip install gspread`).")
                except Exception as e:
                    logger.error(f"ЗАГЛУШКА: Неожиданная ошибка при имитации gspread.service_account: {e}")
            else:
                logger.warning(f"Файл {credentials_path} не найден, пуст или содержит некорректные данные "
                               f"(возможно, из-за гонки воркеров). Инициализация gspread пропущена.")

        def open_spreadsheet(self, name):
            """Имитация открытия таблицы"""
            if not self.client:
                logger.warning("Попытка открыть таблицу без инициализированного клиента.")
                return None
            logger.info(f"ЗАГЛУШКА: Открытие таблицы '{name}'...")
            try:
                self.spreadsheet = self.client.open(name)
                logger.info(f"Таблица '{name}' успешно открыта.")
                return self.spreadsheet
            except Exception as e:
                 logger.error(f"Ошибка открытия таблицы '{name}': {e}")
                 return None

        def create_or_get_worksheet(self, spreadsheet, name):
            """Имитация получения или создания листа"""
            if not spreadsheet:
                logger.warning("Попытка получить лист без объекта таблицы.")
                return None
            logger.info(f"ЗАГЛУШКА: Получение/создание листа '{name}'...")
            try:
                self.worksheet = spreadsheet.worksheet(name) # Попытка получить существующий
                logger.info(f"Лист '{name}' успешно получен.")
            except gspread.WorksheetNotFound:
                 logger.info(f"Лист '{name}' не найден, попытка создать.")
                 try:
                     # В реальном коде здесь будет spreadsheet.add_worksheet(...)
                     self.worksheet = spreadsheet.add_worksheet(title=name, rows="100", cols="10")
                     logger.info(f"Лист '{name}' успешно создан.")
                 except Exception as e_add:
                     logger.error(f"Ошибка создания листа '{name}': {e_add}")
                     self.worksheet = None
            except Exception as e_get:
                 logger.error(f"Ошибка получения листа '{name}': {e_get}")
                 self.worksheet = None
            return self.worksheet

        async def add_status_entry(self, worksheet, user_id, username, status, timestamp):
            """
            Асинхронная имитация добавления строки.
            Использует run_in_executor для вызова синхронного gspread API.
            """
            if not worksheet:
                logger.warning("Попытка добавить запись без объекта листа.")
                return
            logger.debug(f"ЗАГЛУШКА: Добавление строки в лист: {user_id}, {username}, {status}, {timestamp}")
            try:
                # --- ВАЖНО: Использование run_in_executor для синхронного API gspread ---
                # Если ваша версия gspread поддерживает await worksheet.append_row(...), используйте ее напрямую.
                # Иначе, используйте этот подход:
                loop = asyncio.get_running_loop()
                # worksheet.append_row - это СИНХРОННАЯ функция gspread
                await loop.run_in_executor(None, worksheet.append_row, [user_id, username, status, timestamp])
                # -----------------------------------------------------------------------
                logger.debug("Строка успешно добавлена в Google Sheets.")
            except AttributeError:
                 logger.error("ЗАГЛУШКА: Ошибка - у объекта worksheet нет метода 'append_row'. Проверьте инициализацию.")
            except Exception as e:
                 logger.error(f"Ошибка добавления строки в Google Sheets: {e}")


# --- КЛАСС БОТА ---
class AnimatorStatusBot:
    def __init__(self):
        # Загрузка переменных окружения (если есть .env файл)
        load_dotenv()

        # Параметры бота из Config (теперь Config определен выше, либо импортирован, либо как заглушка)
        self.TOKEN = Config.BOT_TOKEN
        self.DATABASE_PATH = 'animator_statuses.db'
        self.VALID_STATUSES = ['в пути', 'на месте', 'закончил']

        # Инициализация DB (запустится в каждом воркере)
        self.setup_database()
        # Инициализация Sheets (запустится в каждом воркере, использует созданный файл)
        # Теперь зависит от успеха инициализации GoogleSheetsManager
        self.setup_google_sheets()

        # Создание приложения Telegram
        self.telegram_app = self.create_telegram_app()

    def setup_database(self):
        """Создание/подключение к базе данных SQLite"""
        try:
            conn = sqlite3.connect(self.DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    status TEXT,
                    timestamp DATETIME
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("База данных SQLite настроена (может дублироваться воркерами).")
        except sqlite3.Error as e:
            logger.error(f"Ошибка настройки SQLite: {e}")

    def setup_google_sheets(self):
        """Настройка подключения к Google Sheets с использованием менеджера."""
        self.sheets_manager = None
        self.status_worksheet = None

        # GOOGLE_CREDS_AVAILABLE проверяет, был ли JSON прочитан из env/записан
        if GOOGLE_CREDS_AVAILABLE:
            try:
                # Создаем экземпляр менеджера (он сам обработает ошибки чтения файла)
                self.sheets_manager = GoogleSheetsManager(credentials_path=CREDENTIALS_FILE_PATH)

                # Проверяем, удалось ли менеджеру инициализировать клиент gspread
                if self.sheets_manager and self.sheets_manager.client:
                    spreadsheet_name = Config.GOOGLE_SHEETS_SPREADSHEET_NAME
                    worksheet_name = Config.GOOGLE_SHEETS_WORKSHEET_NAME

                    spreadsheet = self.sheets_manager.open_spreadsheet(spreadsheet_name)
                    if spreadsheet:
                        self.status_worksheet = self.sheets_manager.create_or_get_worksheet(
                            spreadsheet,
                            worksheet_name
                        )
                        if self.status_worksheet:
                            logger.info(f"Подключение к Google Sheets ({spreadsheet_name}/{worksheet_name}) успешно.")
                        else:
                            logger.warning("Не удалось получить/создать рабочий лист Google Sheets.")
                    else:
                        logger.warning("Не удалось открыть таблицу Google Sheets.")
                else:
                    logger.warning("Клиент Google Sheets не был инициализирован в менеджере (возможно, из-за ошибки чтения credentials или отсутствия gspread).")
            except Exception as e:
                logger.error(f"Неожиданная ошибка при настройке Google Sheets: {e}")
        else:
             logger.warning("Учетные данные Google недоступны (ошибка при создании файла), Google Sheets не будут использоваться.")

    async def save_status(self, user_id: int, username: str, status: str):
        """Асинхронное сохранение статуса в базу данных и Google Sheets"""
        timestamp = datetime.now()
        logger.info(f"Сохранение статуса: User ID={user_id}, Username={username}, Status={status}, Time={timestamp}")

        # Сохранение в SQLite
        try:
            conn = sqlite3.connect(self.DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO statuses (user_id, username, status, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, status, timestamp))
            conn.commit()
            conn.close()
            logger.debug("Статус сохранен в SQLite.")
        except sqlite3.Error as e:
             logger.error(f"Ошибка сохранения в SQLite: {e}")

        # Сохранение в Google Sheets (если менеджер и лист успешно инициализированы)
        if self.sheets_manager and self.status_worksheet:
            try:
                 await self.sheets_manager.add_status_entry(
                    self.status_worksheet,
                    user_id,
                    username,
                    status,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S') # Передаем время как строку
                )
                 # Лог об успешной отправке уже внутри add_status_entry
            except Exception as e:
                 # Лог об ошибке уже внутри add_status_entry
                 logger.error(f"Перехвачена ошибка при вызове add_status_entry: {e}") # Доп. лог на всякий случай
        else:
            logger.debug("Пропуск сохранения в Google Sheets (менеджер или лист не инициализированы).")


    def extract_status(self, text: str) -> Optional[str]:
        """Извлечение первого допустимого статуса из сообщения"""
        if not text:
            return None
        text_lower = text.lower()
        for status in self.VALID_STATUSES:
            # Ищем точное слово или фразу (можно доработать для большей гибкости)
            if status.lower() in text_lower: # Простое вхождение
                 return status
        return None

    def create_telegram_app(self):
        """Создание и настройка приложения python-telegram-bot"""
        application = Application.builder().token(self.TOKEN).build()

        # Регистрация обработчиков
        application.add_handler(CommandHandler('start', self.start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Приложение Telegram создано и обработчики зарегистрированы.")
        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        await update.message.reply_text(
            "Привет! Я бот для отслеживания статусов аниматоров. "
            "Отправь мне статус: 'в пути', 'на месте' или 'закончил'."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих текстовых сообщений"""
        if not update.message or not update.message.text:
            logger.warning("Получено обновление без сообщения или текста.")
            return

        user = update.effective_user
        text = update.message.text
        username = user.username or f"{user.first_name} {user.last_name or ''}".strip() or f"ID:{user.id}"
        logger.info(f"Получено сообщение от {user.id} ({username}): {text}")

        status = self.extract_status(text)
        if status:
            await self.save_status(user.id, username, status)
            await update.message.reply_text(f"Статус '{status}' сохранен.")
        else:
            # Сообщение не содержит статус, можно добавить реакцию или проигнорировать
            logger.debug(f"Статус не найден в сообщении: {text}")
            # await update.message.reply_text("Не распознал статус. Используйте: 'в пути', 'на месте' или 'закончил'.") # Опционально

    async def process_update(self, update_json: Dict):
        """Обработка входящего обновления от вебхука"""
        logger.debug(f"Обработка JSON обновления: {update_json}")
        update = Update.de_json(update_json, self.telegram_app.bot)
        await self.telegram_app.process_update(update)


# --- ЭКЗЕМПЛЯРЫ И ПРИЛОЖЕНИЯ ---
# Создаем экземпляр бота глобально (выполнится в каждом воркере)
# Все инициализации (DB, Sheets) происходят внутри __init__
logger.info("Создание глобального экземпляра AnimatorStatusBot...")
bot_instance = AnimatorStatusBot()
logger.info("Глобальный экземпляр AnimatorStatusBot создан.")

# Создаем Flask приложение (WSGI)
logger.info("Создание экземпляра Flask (WSGI)...")
flask_app = Flask(__name__)
logger.info("Экземпляр Flask создан.")

# --- ASGI Wrapper --- # <--- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ДЛЯ UVICORN
# Создаем ASGI-совместимую обертку вокруг WSGI-приложения Flask
logger.info("Создание ASGI обертки (WsgiToAsgi)...")
asgi_app = WsgiToAsgi(flask_app)
logger.info("ASGI обертка создана.")

# --- МАРШРУТЫ FLASK (Остаются привязанными к flask_app) ---
# Uvicorn через asgi_app будет передавать запросы сюда
@flask_app.route(f'/{bot_instance.TOKEN}', methods=['POST'])
async def webhook():
    """Обработчик вебхука Telegram"""
    logger.debug(f"Входящий запрос на /webhook ({request.method})")
    if request.method == "POST":
        try:
            update_json = request.get_json(force=True)
            if not update_json:
                 logger.warning("Получен пустой JSON в вебхуке.")
                 return 'Bad Request: Empty JSON', 400
            # Используем метод уже созданного глобального экземпляра bot_instance
            await bot_instance.process_update(update_json)
            return 'OK', 200
        except json.JSONDecodeError as json_err:
             logger.error(f"Ошибка декодирования JSON в вебхуке: {json_err}")
             return 'Bad Request: Invalid JSON', 400
        except Exception as e:
            # Логируем полный трейсбек
            logger.exception(f"Критическая ошибка обработки вебхука: {e}")
            # Возвращаем 500, чтобы Telegram понял, что что-то не так, но не банил вебхук сразу
            return 'Internal Server Error', 500
    else:
        # Отвечаем на другие методы (например, GET от браузера)
        logger.warning(f"Недопустимый метод {request.method} для /webhook")
        abort(405) # Method Not Allowed

@flask_app.route('/')
def health_check():
    """Простой health check для Render"""
    logger.debug("Запрос на / (health check)")
    # Можно добавить проверку состояния бота, если нужно
    return "OK - Bot service is running", 200

# --- ТОЧКА ВХОДА ДЛЯ ЛОКАЛЬНОГО ЗАПУСКА (ЧЕРЕЗ POLLING) ---
def main_local():
    """Запускает бота локально через polling (для отладки)"""
    logger.info("="*30)
    logger.info("ЗАПУСК БОТА ЛОКАЛЬНО ЧЕРЕЗ POLLING (НЕ ДЛЯ RENDER)")
    logger.info("="*30)
    # Используем глобальный bot_instance, созданный выше
    bot_instance.telegram_app.run_polling()

if __name__ == '__main__':
     main_local()

# --- ТОЧКА ВХОДА ДЛЯ RENDER ---
# Render (Uvicorn) будет импортировать 'asgi_app' из этого файла.
# Команда запуска в Render должна быть:
# uvicorn bot.main:asgi_app --host 0.0.0.0 --port $PORT --workers 4
# (или с другим числом воркеров)
