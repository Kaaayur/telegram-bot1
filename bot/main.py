import os
import logging
import json  # <-- Импорт для работы с JSON
from typing import List, Dict, Optional
from flask import Flask, request, abort
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import sqlite3
from datetime import datetime
import asyncio

# Предполагаем, что у вас есть эти файлы
try:
    from bot.config import Config
    from bot.google_sheets import GoogleSheetsManager
except ImportError:
    # Заглушки, если файлы не найдены (для базовой работы)
    class Config:
        BOT_TOKEN = "YOUR_BOT_TOKEN" # Замените, если не используете .env
        WEBHOOK_URL = "YOUR_WEBHOOK_URL" # Замените
        GOOGLE_SHEETS_CREDENTIALS_JSON = "{}" # JSON строка по умолчанию
        GOOGLE_SHEETS_SPREADSHEET_NAME = "Статусы Аниматоров"
        GOOGLE_SHEETS_WORKSHEET_NAME = "Статусы"

    class GoogleSheetsManager: # Заглушка
        def __init__(self, credentials_path=None): pass
        def open_spreadsheet(self, name): return None
        def create_or_get_worksheet(self, spreadsheet, name): return None
        def add_status_entry(self, worksheet, user_id, username, status): pass

# --- НАСТРОЙКА ---
CREDENTIALS_FILE_PATH = "credentials.json"  # Имя файла, который мы создадим

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- СОЗДАНИЕ ФАЙЛА УЧЕТНЫХ ДАННЫХ GOOGLE ПРИ ЗАПУСКЕ ---
try:
    # Читаем JSON СТРОКУ из переменной окружения
    google_creds_json_str = os.environ.get(
        'GOOGLE_SHEETS_CREDENTIALS_JSON',
        getattr(Config, 'GOOGLE_SHEETS_CREDENTIALS_JSON', '{}') # Значение по умолчанию из Config
    )
    if not google_creds_json_str or google_creds_json_str == '{}':
        raise ValueError("Переменная окружения GOOGLE_SHEETS_CREDENTIALS_JSON не установлена или пуста!")

    # Пытаемся распарсить JSON, чтобы убедиться, что он валидный
    creds_dict = json.loads(google_creds_json_str)

    # Записываем содержимое в файл credentials.json
    with open(CREDENTIALS_FILE_PATH, "w") as f:
        json.dump(creds_dict, f)
    logger.info(f"✅ Файл учетных данных {CREDENTIALS_FILE_PATH} успешно создан.")
    GOOGLE_CREDS_AVAILABLE = True

except (ValueError, json.JSONDecodeError, FileNotFoundError, OSError) as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА при обработке учетных данных Google: {e}")
    GOOGLE_CREDS_AVAILABLE = False # Google Sheets не будут работать

class AnimatorStatusBot:
    def __init__(self):
        # Загрузка переменных окружения (если есть .env локально)
        load_dotenv()

        # Параметры бота из переменных окружения или Config
        self.TOKEN = os.getenv('BOT_TOKEN', getattr(Config, 'BOT_TOKEN', None))
        # WEBHOOK_URL больше не нужен здесь, Render сам его предоставляет
        self.DATABASE_PATH = 'animator_statuses.db'

        if not self.TOKEN:
            logger.critical("BOT_TOKEN не найден!")
            raise ValueError("BOT_TOKEN не найден!")

        # Допустимые статусы
        self.VALID_STATUSES = ['в пути', 'на месте', 'закончил']

        # Инициализация базы данных и Google Sheets
        self.setup_database()
        self.setup_google_sheets() # Использует созданный credentials.json

        # Создание приложения Telegram
        self.telegram_app = self.create_telegram_app()

    def setup_database(self):
        """Создание базы данных для хранения статусов"""
        try:
            conn = sqlite3.connect(self.DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statuses (
                    user_id INTEGER,
                    username TEXT,
                    status TEXT,
                    timestamp DATETIME
                )
            ''')
            conn.commit()
            conn.close()
            logger.info("База данных SQLite настроена.")
        except sqlite3.Error as e:
             logger.error(f"Ошибка настройки SQLite: {e}")

    def setup_google_sheets(self):
        """Настройка подключения к Google Sheets"""
        self.status_worksheet = None
        if GOOGLE_CREDS_AVAILABLE: # Проверяем, создался ли файл
            try:
                self.sheets_manager = GoogleSheetsManager(credentials_path=CREDENTIALS_FILE_PATH) # Передаем путь
                spreadsheet_name = getattr(Config, 'GOOGLE_SHEETS_SPREADSHEET_NAME', 'Статусы Аниматоров')
                worksheet_name = getattr(Config, 'GOOGLE_SHEETS_WORKSHEET_NAME', 'Статусы')
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
            except Exception as e:
                logger.error(f"Ошибка настройки Google Sheets: {e}")
        else:
             logger.warning("Учетные данные Google недоступны, Google Sheets не будут использоваться.")


    async def save_status(self, user_id: int, username: str, status: str):
        """Сохранение статуса в базу данных и Google Sheets"""
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

        # Сохранение в Google Sheets
        if self.status_worksheet:
            try:
                # Важно: используйте await, если add_status_entry асинхронный
                 await self.sheets_manager.add_status_entry( # ИЛИ просто self.sheets_manager.add_status_entry, если синхронный
                    self.status_worksheet,
                    user_id,
                    username,
                    status,
                    timestamp.strftime('%Y-%m-%d %H:%M:%S') # Передаем время
                )
                 logger.debug("Статус отправлен в Google Sheets.")
            except Exception as e:
                logger.error(f"Ошибка сохранения в Google Sheets: {e}")


    def extract_status(self, text: str) -> Optional[str]:
        """Извлечение статуса из сообщения"""
        if not text:
            return None
        for status in self.VALID_STATUSES:
            if status.lower() in text.lower():
                return status
        return None

    def create_telegram_app(self):
        """Создание Telegram приложения"""
        application = Application.builder().token(self.TOKEN).build()

        # Регистрация обработчиков
        application.add_handler(CommandHandler('start', self.start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        await update.message.reply_text(
            "Привет! Я бот для отслеживания статусов аниматоров. "
            "Отправь мне статус: 'в пути', 'на месте' или 'закончил'."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка входящих сообщений"""
        if not update.message or not update.message.text:
            logger.warning("Получено сообщение без текста.")
            return

        user = update.effective_user
        text = update.message.text
        logger.info(f"Получено сообщение от {user.id} ({user.username or user.first_name}): {text}")

        status = self.extract_status(text)
        if status:
            await self.save_status(user.id, user.username or user.first_name, status)
            await update.message.reply_text(f"Статус '{status}' сохранен.")
        else:
             logger.debug(f"Статус не найден в сообщении: {text}")
             # Можно добавить ответ пользователю, что статус не распознан

    async def process_update(self, update_json):
        """Асинхронная обработка обновления"""
        update = Update.de_json(update_json, self.telegram_app.bot)
        await self.telegram_app.process_update(update)

# --- Flask App для Render ---
# Создаем экземпляр бота глобально, чтобы он был доступен для Flask
bot_instance = AnimatorStatusBot()
flask_app = Flask(__name__)

@flask_app.route(f'/{bot_instance.TOKEN}', methods=['POST'])
async def webhook():
    """Обработчик webhook"""
    if request.method == "POST":
        try:
            update_json = request.get_json(force=True)
            await bot_instance.process_update(update_json)
            return 'OK', 200
        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {e}")
            # Не прерываем работу сервера из-за ошибки в одном обновлении
            return 'Error processing update', 500
    else:
        abort(405) # Method Not Allowed

# --- Точка входа для Render (через Gunicorn или другой WSGI сервер) ---
# Render будет импортировать 'flask_app' из этого файла
# Убедитесь, что ваш Procfile или команда запуска на Render указывает на 'bot:flask_app'

# --- Точка входа для локального запуска (для тестирования) ---
def main_local():
    """Запускает бота локально через polling (для отладки)"""
    logger.info("Запуск бота локально через polling...")
    bot_instance.telegram_app.run_polling()

if __name__ == '__main__':
    # Если файл запускается напрямую, запускаем локально через polling
     main_local()
