# Файл: bot/main.py

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
from asgiref.wsgi import WsgiToAsgi
from zoneinfo import ZoneInfo # <--- ДОБАВЛЕН ИМПОРТ

# --- НАСТРОЙКА ---
CREDENTIALS_FILE_PATH = "credentials.json"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [PID:%(process)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- СОЗДАНИЕ ФАЙЛА УЧЕТНЫХ ДАННЫХ GOOGLE ПРИ ЗАПУСКЕ ---
# (Код без изменений)
GOOGLE_CREDS_AVAILABLE = False
try:
    google_creds_json_str = os.environ.get('GOOGLE_SHEETS_CREDENTIALS_JSON', '{}')
    if not google_creds_json_str or google_creds_json_str == '{}':
        raise ValueError("Переменная окружения GOOGLE_SHEETS_CREDENTIALS_JSON не установлена или пуста!")
    creds_dict = json.loads(google_creds_json_str)
    with open(CREDENTIALS_FILE_PATH, "w") as f:
        json.dump(creds_dict, f)
    logger.info(f"✅ Файл учетных данных {CREDENTIALS_FILE_PATH} успешно создан/перезаписан.")
    GOOGLE_CREDS_AVAILABLE = True
except (ValueError, json.JSONDecodeError, FileNotFoundError, OSError) as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при создании файла {CREDENTIALS_FILE_PATH}: {e}", exc_info=True)

# --- КЛАССЫ КОНФИГУРАЦИИ И МЕНЕДЖЕР GOOGLE SHEETS ---
# (Код без изменений)
try:
    from bot.config import Config
    logger.info("Успешно импортирован Config из bot.config")
except ImportError:
    logger.warning("Не удалось импортировать Config из bot.config. Используется заглушка Config из main.py.")
    class Config:
        BOT_TOKEN = os.getenv('BOT_TOKEN')
        if not BOT_TOKEN: logger.critical("Переменная окружения BOT_TOKEN не установлена!")
        GOOGLE_SHEETS_SPREADSHEET_NAME = os.getenv('GOOGLE_SHEETS_SPREADSHEET_NAME', "АнимельБот")
        GOOGLE_SHEETS_WORKSHEET_NAME = os.getenv('GOOGLE_SHEETS_WORKSHEET_NAME', "Статусы")

try:
    from bot.google_sheets import GoogleSheetsManager
    logger.info("Успешно импортирован GoogleSheetsManager из bot.google_sheets")
    HAS_GOOGLE_SHEETS_MANAGER = True
except ImportError:
    logger.critical("❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать GoogleSheetsManager из bot.google_sheets. Работа с таблицами невозможна.")
    HAS_GOOGLE_SHEETS_MANAGER = False
    class GoogleSheetsManager: pass


# --- КЛАСС БОТА ---
class AnimatorStatusBot:
    def __init__(self):
        load_dotenv()
        self.TOKEN = Config.BOT_TOKEN
        if not self.TOKEN: raise ValueError("Не удалось получить токен бота из Config.")

        self.DATABASE_PATH = 'animator_statuses.db'
        self.VALID_STATUSES = ['в пути', 'на месте', 'закончил']
        self._app_initialized = False

        # !!! ЗАПОЛНИТЕ ЭТОТ СЛОВАРЬ ВАШИМИ ДАННЫМИ !!!
        self.artist_mapping = {
            283779327: "Егор",
            413165965: "Настя",
            6292548875: "Яна",
           
            # telegram_user_id: "Имя Фамилия или Псевдоним"
        }
        logger.info(f"Загружена карта артистов: {len(self.artist_mapping)} записей")

        self.setup_database()
        self.setup_google_sheets()
        self.telegram_app = self.create_telegram_app()
        logger.info("Экземпляр AnimatorStatusBot создан. Инициализация Telegram App будет при первом запросе.")

    def setup_database(self):
        # (Код без изменений)
        try:
            conn = sqlite3.connect(self.DATABASE_PATH); cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS statuses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, status TEXT NOT NULL, timestamp DATETIME NOT NULL)''')
            conn.commit(); conn.close()
            logger.info(f"База данных SQLite '{self.DATABASE_PATH}' настроена.")
        except sqlite3.Error as e: logger.error(f"Ошибка настройки SQLite '{self.DATABASE_PATH}': {e}")

    def setup_google_sheets(self):
        # (Код без изменений)
        self.sheets_manager = None
        self.status_worksheet = None
        if HAS_GOOGLE_SHEETS_MANAGER:
            if GOOGLE_CREDS_AVAILABLE:
                logger.info("Учетные данные Google доступны, попытка настройки Google Sheets...")
                try:
                    self.sheets_manager = GoogleSheetsManager(credentials_path=CREDENTIALS_FILE_PATH)
                    if hasattr(self.sheets_manager, 'client') and self.sheets_manager.client:
                        spreadsheet_name = Config.GOOGLE_SHEETS_SPREADSHEET_NAME
                        worksheet_name = Config.GOOGLE_SHEETS_WORKSHEET_NAME
                        logger.info(f"Попытка открыть таблицу '{spreadsheet_name}' и лист '{worksheet_name}'...")
                        spreadsheet = self.sheets_manager.open_spreadsheet(spreadsheet_name)
                        if spreadsheet:
                            worksheet = self.sheets_manager.create_or_get_worksheet(spreadsheet, worksheet_name)
                            if worksheet:
                                self.status_worksheet = worksheet
                                logger.info(f"Подключение к Google Sheets ({spreadsheet_name}/{worksheet_name}) успешно установлено.")
                            else: logger.warning("Не удалось получить или создать рабочий лист Google Sheets.")
                        else: logger.warning("Не удалось открыть таблицу Google Sheets.")
                    else: logger.warning("Менеджер Google Sheets создан, но клиент gspread не был инициализирован.")
                except Exception as e: logger.error(f"Неожиданная ошибка при настройке Google Sheets: {e}", exc_info=True)
            else: logger.warning("Учетные данные Google недоступны. Google Sheets не будут использоваться.")
        else: logger.warning("Класс GoogleSheetsManager не импортирован. Работа с Google Sheets невозможна.")


    async def save_status(self, user_id: int, username: str, status: str):
        """Асинхронно сохраняет статус в SQLite и Google Sheets с реальным именем и МОСКОВСКИМ временем."""

        # --- ИЗМЕНЕНО: Получаем время по Москве ---
        moscow_tz = ZoneInfo("Europe/Moscow")
        timestamp_msk = datetime.now(moscow_tz) # Текущее время сразу в нужной таймзоне
        timestamp_str = timestamp_msk.strftime('%Y-%m-%d %H:%M:%S') # Строка для Google Sheets
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        real_artist_name = self.artist_mapping.get(user_id, username or f"ID:{user_id}")
        # --- ИЗМЕНЕНО: Логируем время MSK ---
        logger.info(f"Сохранение статуса: User ID={user_id}, TG Username='{username}', Real Name='{real_artist_name}', Status='{status}', Time (MSK)={timestamp_msk}")
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        # Сохранение в SQLite (передаем объект datetime, sqlite3 его обработает)
        try:
            conn = sqlite3.connect(self.DATABASE_PATH); cursor = conn.cursor()
            # --- ИЗМЕНЕНО: Передаем timestamp_msk ---
            cursor.execute('INSERT INTO statuses (user_id, username, status, timestamp) VALUES (?, ?, ?, ?)',(user_id, username, status, timestamp_msk))
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
            conn.commit(); conn.close()
            logger.debug("Статус успешно сохранен в SQLite.")
        except sqlite3.Error as e: logger.error(f"Ошибка сохранения статуса в SQLite: {e}")

        # Сохранение в Google Sheets (передаем строку с московским временем)
        if self.sheets_manager and self.status_worksheet:
            logger.debug("Попытка сохранения статуса в Google Sheets...")
            try:
                 # Передаем те же аргументы, но timestamp_str теперь содержит московское время
                 await self.sheets_manager.add_status_entry(
                     real_artist_name,
                     status,
                     timestamp_str # Эта строка уже отформатирована с учетом MSK
                 )
            except Exception as e: logger.error(f"Ошибка при вызове add_status_entry для Google Sheets: {e}", exc_info=True)
        else: logger.debug("Пропуск сохранения в Google Sheets.")

    def extract_status(self, text: str) -> Optional[str]:
        # (Код без изменений)
        if not text: return None
        text_lower = text.lower()
        for status in self.VALID_STATUSES:
            if status.lower() in text_lower: return status
        return None

    def create_telegram_app(self):
        # (Код без изменений)
        if not self.TOKEN: raise ValueError("Токен бота не определен.")
        application = Application.builder().token(self.TOKEN).build()
        application.add_handler(CommandHandler('start', self.start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.info("Экземпляр приложения Telegram создан, обработчики добавлены.")
        return application

    # --- Обработчики Telegram ---
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # (Код без изменений)
        user = update.effective_user
        logger.info(f"Получена команда /start от пользователя {user.id} ({user.username})")
        await update.message.reply_text(f"Привет! Отправь статус: '{', '.join(self.VALID_STATUSES)}'.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # (Код без изменений)
        if not update.message or not update.message.text: return
        user = update.effective_user; text = update.message.text
        username = user.username or f"{user.first_name} {user.last_name or ''}".strip() or f"ID:{user.id}"
        logger.info(f"Получено сообщение от {user.id} ({username}): '{text}'")
        status = self.extract_status(text)
        if status:
            logger.info(f"Распознан статус: '{status}'")
            await self.save_status(user.id, username, status)
            await update.message.reply_text(f"✅ Статус '{status}' сохранен.")
        else: logger.debug(f"Допустимый статус не найден в сообщении.")

    async def _ensure_initialized(self):
        # (Код без изменений)
        if not self._app_initialized:
            logger.info("Выполняется первая инициализация приложения Telegram (Application.initialize)...")
            try:
                await self.telegram_app.initialize()
                self._app_initialized = True
                logger.info("Приложение Telegram успешно инициализировано при первом использовании.")
            except Exception as e:
                logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ПОПЫТКЕ ЛЕНИВОЙ ИНИЦИАЛИЗАЦИИ TELEGRAM: {e}", exc_info=True)
                raise RuntimeError("Failed to initialize Telegram Application on first use") from e

    async def process_update(self, update_json: Dict):
        # (Код без изменений)
        logger.debug(f"Обработка JSON обновления: {update_json}")
        await self._ensure_initialized()
        update = Update.de_json(update_json, self.telegram_app.bot)
        await self.telegram_app.process_update(update)
        logger.debug("Обновление успешно передано в telegram_app.process_update")


# --- ГЛОБАЛЬНЫЕ ЭКЗЕМПЛЯРЫ И ASGI/WSGI ПРИЛОЖЕНИЯ ---
# (Код без изменений)
logger.info("Создание глобального экземпляра AnimatorStatusBot...")
try:
    bot_instance = AnimatorStatusBot()
    logger.info("Глобальный экземпляр AnimatorStatusBot успешно создан.")
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ СОЗДАНИИ ЭКЗЕМПЛЯРА БОТА: {e}", exc_info=True)
    bot_instance = None

logger.info("Создание экземпляра Flask (WSGI)...")
flask_app = Flask(__name__)
logger.info("Экземпляр Flask создан.")

logger.info("Создание ASGI обертки (WsgiToAsgi) для Flask...")
asgi_app = WsgiToAsgi(flask_app)
logger.info("ASGI обертка создана.")

# --- МАРШРУТЫ FLASK ---
# (Код без изменений)
@flask_app.route('/webhook', methods=['POST'])
async def webhook():
    worker_pid = os.getpid()
    logger.debug(f"[Worker {worker_pid}] Входящий запрос на /webhook ({request.method}) от {request.remote_addr}")
    if bot_instance is None:
         logger.error(f"[Worker {worker_pid}] /webhook: Экземпляр бота не был создан!")
         return 'Internal Server Error: Bot instance not available', 500
    if request.method == "POST":
        try:
            update_json = request.get_json(force=True)
            if not update_json:
                 logger.warning(f"[Worker {worker_pid}] /webhook: Пустой JSON.")
                 return 'Bad Request: Empty JSON', 400
            await bot_instance.process_update(update_json)
            logger.info(f"[Worker {worker_pid}] /webhook: Вебхук успешно обработан.")
            return 'OK', 200
        except json.JSONDecodeError as json_err:
             logger.error(f"[Worker {worker_pid}] /webhook: Ошибка декодирования JSON: {json_err}")
             return 'Bad Request: Invalid JSON', 400
        except RuntimeError as rt_err:
             if "Failed to initialize Telegram Application" in str(rt_err) or "Application was not initialized" in str(rt_err):
                  logger.exception(f"[Worker {worker_pid}] /webhook: КРИТИЧЕСКАЯ ОШИБКА - Не удалось инициализировать приложение Telegram: {rt_err}")
                  return 'Internal Server Error - TG App Initialization Failed', 500
             else:
                  logger.exception(f"[Worker {worker_pid}] /webhook: Неожиданная ошибка RuntimeError: {rt_err}")
                  return 'Internal Server Error', 500
        except Exception as e:
            logger.exception(f"[Worker {worker_pid}] /webhook: Критическая ошибка обработки: {e}")
            return 'Internal Server Error', 500
    else:
        logger.warning(f"[Worker {worker_pid}] /webhook: Недопустимый метод {request.method}")
        abort(405)

@flask_app.route('/')
def health_check():
    logger.debug("Запрос на / (health check)")
    bot_status = "created" if bot_instance else "NOT CREATED"
    return f"OK - Bot service is running (Bot instance: {bot_status})", 200

# --- ТОЧКА ВХОДА ДЛЯ ЛОКАЛЬНОГО ЗАПУСКА (ЧЕРЕЗ POLLING) ---
# (Код без изменений)
def main_local():
    logger.info("="*30); logger.info("ЗАПУСК БОТА ЛОКАЛЬНО ЧЕРЕЗ POLLING"); logger.info("="*30)
    if bot_instance and bot_instance.telegram_app:
         logger.info("Используется глобальный экземпляр бота. Запуск polling...")
         bot_instance.telegram_app.run_polling()
         logger.info("Polling завершен.")
    else: logger.critical("Не удалось запустить polling: экземпляр бота не создан.")

if __name__ == '__main__':
     main_local()

# --- ТОЧКА ВХОДА ДЛЯ RENDER (UVICORN) ---
# uvicorn bot.main:asgi_app --host 0.0.0.0 --port $PORT --workers 1
