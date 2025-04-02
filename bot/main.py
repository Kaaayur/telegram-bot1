# /opt/render/project/src/bot/main.py

import os
import logging
import json
from typing import List, Dict, Optional
from flask import Flask, request, abort
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import asyncio
from asgiref.wsgi import WsgiToAsgi # Для обертки Flask под ASGI

# --- НАСТРОЙКА ---
CREDENTIALS_FILE_PATH = "credentials.json"  # Имя файла учетных данных Google

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, # Установите DEBUG для более подробных логов
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- СОЗДАНИЕ ФАЙЛА УЧЕТНЫХ ДАННЫХ GOOGLE ПРИ ЗАПУСКЕ ---
# Этот блок выполняется при загрузке модуля каждым воркером Uvicorn
GOOGLE_CREDS_AVAILABLE = False # Флаг доступности учетных данных
try:
    # Читаем JSON СТРОКУ из переменной окружения
    google_creds_json_str = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON', '{}')
    if not google_creds_json_str or google_creds_json_str == '{}':
        raise ValueError("Переменная окружения GOOGLE_SHEETS_CREDENTIALS_JSON не установлена или пуста!")

    # Пытаемся распарсить JSON для валидации
    creds_dict = json.loads(google_creds_json_str)

    # Записываем содержимое в файл credentials.json
    # ВАЖНО: Возможна гонка состояний между воркерами, но обычно последний записавший побеждает.
    with open(CREDENTIALS_FILE_PATH, "w") as f:
        json.dump(creds_dict, f)
    logger.info(f"✅ Файл учетных данных {CREDENTIALS_FILE_PATH} успешно создан/перезаписан.")
    GOOGLE_CREDS_AVAILABLE = True # Устанавливаем флаг, если запись прошла успешно

except (ValueError, json.JSONDecodeError, FileNotFoundError, OSError) as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при создании файла {CREDENTIALS_FILE_PATH} из переменной окружения: {e}")
    # GOOGLE_CREDS_AVAILABLE останется False


# --- КЛАССЫ КОНФИГУРАЦИИ И МЕНЕДЖЕР GOOGLE SHEETS ---
# Сначала пытаемся импортировать ваши реальные классы из bot.*
# Если не получается, используем заглушки, определенные ниже.
try:
    from bot.config import Config
    logger.info("Успешно импортирован Config из bot.config")
    from bot.google_sheets import GoogleSheetsManager
    logger.info("Успешно импортирован GoogleSheetsManager из bot.google_sheets")

except ImportError:
    logger.warning("Не удалось импортировать Config или GoogleSheetsManager из bot.*. Используются заглушки, определенные в main.py.")

    # --- Заглушка Config ---
    class Config:
        """Класс конфигурации (заглушка)."""
        # Получаем токен из переменной окружения BOT_TOKEN, обязательно установите ее на Render!
        BOT_TOKEN = os.getenv('BOT_TOKEN')
        if not BOT_TOKEN:
            logger.critical("Переменная окружения BOT_TOKEN не установлена! Бот не сможет запуститься.")
            # Можно либо выбросить исключение, либо оставить None, но бот упадет позже.
            # raise ValueError("Переменная окружения BOT_TOKEN не установлена!")

        # Имена для Google Sheets (если используется)
        GOOGLE_SHEETS_SPREADSHEET_NAME = os.getenv('GOOGLE_SHEETS_SPREADSHEET_NAME', "АнимельБот") # Имя таблицы
        GOOGLE_SHEETS_WORKSHEET_NAME = os.getenv('GOOGLE_SHEETS_WORKSHEET_NAME', "Статусы")     # Имя листа

        # GOOGLE_SHEETS_CREDENTIALS_JSON больше не нужен здесь, он читается напрямую выше

    # --- Доработанная Заглушка GoogleSheetsManager ---
    class GoogleSheetsManager:
        """
        Заглушка менеджера Google Sheets.
        НЕ записывает данные, только логирует. Замените реальной реализацией.
        """
        def __init__(self, credentials_path=None):
            self.client = None
            self.spreadsheet = None
            self.worksheet = None
            self._credentials_path = credentials_path
            logger.info(f"[ЗАГЛУШКА] Попытка инициализации GoogleSheetsManager с файлом: {credentials_path}")

            # Проверяем доступность учетных данных перед имитацией инициализации
            if GOOGLE_CREDS_AVAILABLE and self._credentials_path and os.path.exists(self._credentials_path):
                logger.info("[ЗАГЛУШКА] Файл учетных данных найден. Имитация успешной инициализации клиента gspread.")
                # В реальном коде здесь будет:
                # import gspread
                # try:
                #     self.client = gspread.service_account(filename=self._credentials_path)
                #     logger.info("Клиент gspread УСПЕШНО инициализирован.")
                # except Exception as e:
                #     logger.error(f"Ошибка инициализации gspread: {e}")
                #     self.client = None
                self.client = True # Просто флаг для заглушки
            else:
                logger.warning(f"[ЗАГЛУШКА] Файл учетных данных '{self._credentials_path}' недоступен. Инициализация gspread пропущена.")

        def open_spreadsheet(self, name):
            """Имитация открытия таблицы"""
            if not self.client:
                logger.warning("[ЗАГЛУШКА] Попытка открыть таблицу без инициализированного клиента.")
                return None
            logger.info(f"[ЗАГЛУШКА] Открытие таблицы '{name}'...")
            # В реальном коде: self.spreadsheet = self.client.open(name)
            self.spreadsheet = True # Имитация успеха
            logger.info(f"[ЗАГЛУШКА] Таблица '{name}' 'успешно открыта'.")
            return self # Возвращаем self для цепочки вызовов

        def create_or_get_worksheet(self, spreadsheet_obj_ignored, name):
            """Имитация получения или создания листа"""
            if not self.client or not self.spreadsheet:
                logger.warning("[ЗАГЛУШКА] Попытка получить лист без клиента/таблицы.")
                return None
            logger.info(f"[ЗАГЛУШКА] Получение/создание листа '{name}'...")
            # В реальном коде логика с try/except WorksheetNotFound
            self.worksheet = True # Имитация успеха
            logger.info(f"[ЗАГЛУШКА] Лист '{name}' 'успешно получен/создан'.")
            return self # Возвращаем self для цепочки вызовов

        async def add_status_entry(self, worksheet_obj_ignored, user_id, username, status, timestamp):
            """Асинхронная имитация добавления строки."""
            if not self.client or not self.worksheet:
                logger.warning("[ЗАГЛУШКА] Попытка добавить запись без клиента/листа.")
                return
            logger.info(f"[ЗАГЛУШКА] Добавление строки в лист: {user_id}, {username}, {status}, {timestamp}")
            # В реальном коде с gspread (синхронным):
            # try:
            #     loop = asyncio.get_running_loop()
            #     # worksheet_obj_ignored здесь будет реальным объектом worksheet
            #     await loop.run_in_executor(None, worksheet_obj_ignored.append_row, [user_id, username, status, timestamp])
            #     logger.debug("Строка успешно добавлена в Google Sheets.")
            # except Exception as e:
            #     logger.error(f"Ошибка добавления строки в Google Sheets: {e}")
            await asyncio.sleep(0.01) # Имитация небольшой задержки
            logger.debug("[ЗАГЛУШКА] Строка 'успешно добавлена' в Google Sheets.")


# --- КЛАСС БОТА ---
class AnimatorStatusBot:
    """Основной класс бота, управляющий состоянием и обработчиками."""
    def __init__(self):
        # Загрузка переменных из .env файла, если он есть (полезно для локальной разработки)
        load_dotenv()

        # Используем Config (импортированный или заглушку)
        self.TOKEN = Config.BOT_TOKEN
        if not self.TOKEN:
             # Если токен так и не определился, бот работать не сможет.
             # Лог об этом уже был выше, но можно и тут остановить.
             raise ValueError("Не удалось получить токен бота из Config. Проверьте переменную окружения BOT_TOKEN.")

        self.DATABASE_PATH = 'animator_statuses.db' # Путь к файлу SQLite
        self.VALID_STATUSES = ['в пути', 'на месте', 'закончил'] # Допустимые статусы

        # Инициализация подсистем (выполняется в каждом воркере)
        self.setup_database()
        self.setup_google_sheets()
        self.telegram_app = self.create_telegram_app()

        # --- ЯВНАЯ ИНИЦИАЛИЗАЦИЯ TELEGRAM ПРИЛОЖЕНИЯ ---
        # Необходимо при использовании вебхуков с внешними фреймворками (Flask/Uvicorn),
        # так как методы run_polling/run_webhook не вызываются.
        logger.info("Инициализация приложения Telegram (Application.initialize)...")
        try:
            # Получаем event loop, запущенный ASGI-сервером (Uvicorn)
            loop = asyncio.get_running_loop()
            # Запускаем асинхронную initialize() синхронно в этом цикле
            loop.run_until_complete(self.telegram_app.initialize())
            logger.info("Приложение Telegram успешно инициализировано.")
        except RuntimeError as e:
             # Эта ошибка может возникнуть, если цикл еще не запущен (маловероятно с Uvicorn)
             logger.critical(f"НЕ УДАЛОСЬ ПОЛУЧИТЬ ТЕКУЩИЙ EVENT LOOP ДЛЯ ИНИЦИАЛИЗАЦИИ TELEGRAM: {e}", exc_info=True)
             # В этом случае бот не сможет работать, можно остановить воркер
             # raise SystemExit("Не удалось инициализировать Telegram из-за отсутствия event loop")
        except Exception as e:
            # Ловим другие возможные ошибки инициализации (проблемы с токеном, сетью и т.д.)
            logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ИНИЦИАЛИЗАЦИИ ПРИЛОЖЕНИЯ TELEGRAM: {e}", exc_info=True)
            # Можно остановить воркер, так как без инициализации бот бесполезен
            # raise SystemExit(f"Критическая ошибка инициализации Telegram: {e}")
        # --- КОНЕЦ БЛОКА ИНИЦИАЛИЗАЦИИ ---

    def setup_database(self):
        """Создает таблицу SQLite, если она не существует."""
        try:
            conn = sqlite3.connect(self.DATABASE_PATH)
            cursor = conn.cursor()
            # Добавлено PRIMARY KEY AUTOINCREMENT для уникальности записей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    status TEXT NOT NULL,
                    timestamp DATETIME NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"База данных SQLite '{self.DATABASE_PATH}' настроена.")
        except sqlite3.Error as e:
            logger.error(f"Ошибка настройки SQLite '{self.DATABASE_PATH}': {e}")

    def setup_google_sheets(self):
        """Инициализирует менеджер Google Sheets."""
        self.sheets_manager = None
        self.status_worksheet = None # Храним ссылку на рабочий лист для удобства

        # Проверяем, были ли учетные данные успешно загружены/созданы ранее
        if GOOGLE_CREDS_AVAILABLE:
            logger.info("Учетные данные Google доступны, попытка настройки Google Sheets...")
            try:
                # Создаем экземпляр менеджера (реального или заглушки)
                self.sheets_manager = GoogleSheetsManager(credentials_path=CREDENTIALS_FILE_PATH)

                # Проверяем, удалось ли менеджеру инициализировать свой клиент (gspread)
                if self.sheets_manager and self.sheets_manager.client:
                    spreadsheet_name = Config.GOOGLE_SHEETS_SPREADSHEET_NAME
                    worksheet_name = Config.GOOGLE_SHEETS_WORKSHEET_NAME
                    logger.info(f"Попытка открыть таблицу '{spreadsheet_name}' и лист '{worksheet_name}'...")

                    # Используем методы менеджера
                    spreadsheet = self.sheets_manager.open_spreadsheet(spreadsheet_name)
                    if spreadsheet:
                        # Получаем/создаем рабочий лист
                        # Передаем сам объект spreadsheet (или имитацию в заглушке)
                        worksheet = self.sheets_manager.create_or_get_worksheet(spreadsheet, worksheet_name)
                        if worksheet:
                            # Сохраняем ссылку на рабочий лист для использования в save_status
                            self.status_worksheet = worksheet
                            logger.info(f"Подключение к Google Sheets ({spreadsheet_name}/{worksheet_name}) успешно установлено.")
                        else:
                            logger.warning("Не удалось получить или создать рабочий лист Google Sheets.")
                    else:
                        logger.warning("Не удалось открыть таблицу Google Sheets.")
                else:
                    logger.warning("Клиент Google Sheets (gspread) не был инициализирован в менеджере. Проверьте учетные данные или логи заглушки.")
            except Exception as e:
                logger.error(f"Неожиданная ошибка при настройке Google Sheets: {e}", exc_info=True)
        else:
             logger.warning("Учетные данные Google недоступны (ошибка при создании файла). Google Sheets не будут использоваться.")

    async def save_status(self, user_id: int, username: str, status: str):
        """Асинхронно сохраняет статус в SQLite и (если настроено) в Google Sheets."""
        timestamp = datetime.now()
        logger.info(f"Сохранение статуса: User ID={user_id}, Username='{username}', Status='{status}', Time={timestamp}")

        # Сохранение в SQLite (синхронная операция, но быстрая)
        try:
            conn = sqlite3.connect(self.DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO statuses (user_id, username, status, timestamp) VALUES (?, ?, ?, ?)',
                (user_id, username, status, timestamp)
            )
            conn.commit()
            conn.close()
            logger.debug("Статус успешно сохранен в SQLite.")
        except sqlite3.Error as e:
             logger.error(f"Ошибка сохранения статуса в SQLite: {e}")

        # Асинхронное сохранение в Google Sheets (если менеджер и лист были успешно инициализированы)
        if self.sheets_manager and self.status_worksheet:
            logger.debug("Попытка сохранения статуса в Google Sheets...")
            try:
                 # Вызываем асинхронный метод менеджера
                 await self.sheets_manager.add_status_entry(
                    self.status_worksheet, # Передаем сохраненный объект листа (или его имитацию)
                    user_id,
                    username,
                    status,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S') # Передаем время как строку
                )
                 # Лог об успехе или ошибке должен быть внутри add_status_entry
            except Exception as e:
                 # Логируем ошибку на случай, если она возникла при *вызове* add_status_entry
                 logger.error(f"Ошибка при вызове add_status_entry для Google Sheets: {e}", exc_info=True)
        else:
            logger.debug("Пропуск сохранения в Google Sheets (менеджер или лист не инициализированы).")


    def extract_status(self, text: str) -> Optional[str]:
        """Извлекает первый найденный допустимый статус из текста сообщения."""
        if not text:
            return None
        text_lower = text.lower() # Сравниваем в нижнем регистре
        for status in self.VALID_STATUSES:
            # Простое вхождение подстроки. Можно усложнить (например, регулярными выражениями), если нужно.
            if status.lower() in text_lower:
                 return status # Возвращаем первый найденный
        return None # Статус не найден

    def create_telegram_app(self):
        """Создает и настраивает экземпляр telegram.ext.Application."""
        if not self.TOKEN:
             logger.critical("Невозможно создать приложение Telegram: токен отсутствует.")
             raise ValueError("Токен бота не определен.")

        application = Application.builder().token(self.TOKEN).build()

        # Регистрация обработчиков команд и сообщений
        application.add_handler(CommandHandler('start', self.start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        logger.info("Экземпляр приложения Telegram создан, обработчики добавлены.")
        return application

    # --- Обработчики Telegram ---
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start."""
        user = update.effective_user
        logger.info(f"Получена команда /start от пользователя {user.id} ({user.username})")
        await update.message.reply_text(
            "Привет! Я бот для отслеживания статусов аниматоров.\n"
            f"Просто отправь мне свой статус: '{', '.join(self.VALID_STATUSES)}'."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений."""
        # Проверяем наличие сообщения и текста
        if not update.message or not update.message.text:
            logger.warning("Получено обновление без сообщения или текста (возможно, редактирование или другой тип).")
            return

        user = update.effective_user
        text = update.message.text

        # Формируем имя пользователя для логов и записи
        username = user.username or f"{user.first_name} {user.last_name or ''}".strip() or f"ID:{user.id}"
        logger.info(f"Получено сообщение от {user.id} ({username}): '{text}'")

        # Пытаемся извлечь статус
        status = self.extract_status(text)
        if status:
            logger.info(f"Распознан статус: '{status}'")
            # Сохраняем статус асинхронно
            await self.save_status(user.id, username, status)
            # Отвечаем пользователю
            await update.message.reply_text(f"✅ Статус '{status}' успешно сохранен.")
        else:
            # Если статус не распознан, можно либо ничего не делать, либо ответить
            logger.debug(f"Допустимый статус не найден в сообщении.")
            # Опционально: ответить пользователю, что статус не распознан
            # await update.message.reply_text(
            #     f"Не удалось распознать статус. Пожалуйста, используйте один из: '{', '.join(self.VALID_STATUSES)}'."
            # )

    async def process_update(self, update_json: Dict):
        """
        Принимает JSON обновления от вебхука, десериализует его
        и передает в обработчик python-telegram-bot.
        """
        logger.debug(f"Обработка JSON обновления: {update_json}")
        try:
            update = Update.de_json(update_json, self.telegram_app.bot)
            # Передаем десериализованное обновление в PTB для обработки через добавленные хендлеры
            await self.telegram_app.process_update(update)
            logger.debug("Обновление успешно передано в telegram_app.process_update")
        except Exception as e:
            # Ловим возможные ошибки при десериализации или внутренней обработке PTB
            logger.error(f"Ошибка при обработке обновления PTB: {e}", exc_info=True)
            # Не бросаем исключение дальше, чтобы Flask мог вернуть OK или другую ошибку вебхуку.


# --- ГЛОБАЛЬНЫЕ ЭКЗЕМПЛЯРЫ И ASGI/WSGI ПРИЛОЖЕНИЯ ---

# Создаем единственный экземпляр бота при загрузке модуля.
# Инициализация DB, Sheets и Telegram App происходит внутри __init__.
# Этот код выполнится в КАЖДОМ воркере Uvicorn.
logger.info("Создание глобального экземпляра AnimatorStatusBot...")
try:
    bot_instance = AnimatorStatusBot()
    logger.info("Глобальный экземпляр AnimatorStatusBot успешно создан и инициализирован.")
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ СОЗДАНИИ ЭКЗЕМПЛЯРА БОТА: {e}", exc_info=True)
    # Если бот не создался, приложение не сможет работать. Можно остановить.
    # raise SystemExit(f"Не удалось создать экземпляр бота: {e}")
    bot_instance = None # Устанавливаем в None, чтобы последующий код мог это проверить

# Создаем Flask приложение (WSGI)
logger.info("Создание экземпляра Flask (WSGI)...")
flask_app = Flask(__name__)
logger.info("Экземпляр Flask создан.")

# Создаем ASGI-совместимую обертку вокруг WSGI-приложения Flask
# Uvicorn будет запускать именно 'asgi_app'
logger.info("Создание ASGI обертки (WsgiToAsgi) для Flask...")
asgi_app = WsgiToAsgi(flask_app)
logger.info("ASGI обертка создана.")


# --- МАРШРУТЫ FLASK (Обрабатываются через asgi_app -> flask_app) ---

@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    """Обработчик вебхука Telegram. Принимает POST запросы от Telegram."""
    logger.debug(f"Входящий запрос на /webhook ({request.method}) от {request.remote_addr}")

    # Проверяем, был ли успешно создан экземпляр бота
    if bot_instance is None:
         logger.error("Обработчик /webhook вызван, но экземпляр бота не был создан!")
         return 'Internal Server Error: Bot instance not available', 500

    # Проверяем метод запроса
    if request.method == "POST":
        try:
            # Получаем JSON из тела запроса
            update_json = request.get_json(force=True)
            if not update_json:
                 logger.warning("Получен пустой JSON в теле запроса вебхука.")
                 return 'Bad Request: Empty JSON', 400

            # Передаем JSON в метод обработки экземпляра бота
            await bot_instance.process_update(update_json)

            # Если process_update не вызвал исключений, считаем обработку успешной
            logger.info("Вебхук успешно обработан.")
            # Возвращаем Telegram статус 200 OK, чтобы он знал, что обновление доставлено
            return 'OK', 200

        except json.JSONDecodeError as json_err:
             # Ошибка парсинга JSON
             logger.error(f"Ошибка декодирования JSON в вебхуке: {json_err}")
             return 'Bad Request: Invalid JSON', 400
        except Exception as e:
            # Ловим любые другие неожиданные ошибки во время обработки
            logger.exception(f"Критическая ошибка обработки вебхука: {e}")
            # Возвращаем 500, чтобы сигнализировать о проблеме на нашей стороне
            return 'Internal Server Error', 500
    else:
        # Если пришел не POST запрос (например, GET из браузера)
        logger.warning(f"Получен недопустимый метод {request.method} для /webhook")
        # Возвращаем ошибку 405 Method Not Allowed
        abort(405)

@flask_app.route('/')
def health_check():
    """
    Простой маршрут для проверки работоспособности сервиса (health check).
    Render или другие системы мониторинга могут его использовать.
    """
    logger.debug("Запрос на / (health check)")
    # Можно добавить более сложную проверку, если нужно (например, доступность DB)
    # Но базовая проверка, что Flask отвечает, уже полезна.
    return "OK - AnimatorStatusBot service is running", 200

# --- ТОЧКА ВХОДА ДЛЯ ЛОКАЛЬНОГО ЗАПУСКА (ЧЕРЕЗ POLLING) ---
def main_local():
    """
    Запускает бота локально для отладки, используя метод polling.
    НЕ ИСПОЛЬЗУЕТСЯ НА RENDER. Запускается только если файл выполнить напрямую: python bot/main.py
    """
    logger.info("="*30)
    logger.info("ЗАПУСК БОТА ЛОКАЛЬНО ЧЕРЕЗ POLLING (ДЛЯ ОТЛАДКИ)")
    logger.info("="*30)

    if bot_instance and bot_instance.telegram_app:
         logger.info("Используется глобальный экземпляр бота. Запуск polling...")
         # run_polling сам обрабатывает инициализацию, если она еще не была сделана,
         # и запускает бесконечный цикл получения обновлений.
         # Он также корректно обрабатывает сигналы завершения (Ctrl+C).
         bot_instance.telegram_app.run_polling()
         logger.info("Polling завершен.")
    else:
         logger.critical("Не удалось запустить polling: экземпляр бота или приложения Telegram не был создан.")

if __name__ == '__main__':
     # Этот блок выполнится, только если скрипт запущен напрямую
     main_local()

# --- ТОЧКА ВХОДА ДЛЯ RENDER (UVICORN) ---
# Render будет использовать команду запуска, указанную в настройках сервиса, например:
# uvicorn bot.main:asgi_app --host 0.0.0.0 --port $PORT --workers 1
#
# Uvicorn импортирует объект 'asgi_app' из этого файла и запустит его.
# Код внутри if __name__ == '__main__': на Render выполняться НЕ будет.
