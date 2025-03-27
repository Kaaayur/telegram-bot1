import os
import logging
from typing import List, Dict
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
import sqlite3
from datetime import datetime, timedelta

from bot.config import Config
from bot.google_sheets import GoogleSheetsManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AnimatorStatusBot:
    def __init__(self):
        # Загрузка переменных окружения
        load_dotenv()
        
        # Параметры бота
        self.TOKEN = os.getenv('BOT_TOKEN', Config.BOT_TOKEN)
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL', Config.WEBHOOK_URL)
        self.DATABASE_PATH = 'animator_statuses.db'
        
        # Допустимые статусы
        self.VALID_STATUSES = ['в пути', 'на месте', 'закончил']
        
        # Инициализация базы данных и Google Sheets
        self.setup_database()
        self.setup_google_sheets()
        
        # Создание приложения Telegram
        self.app = None

    def setup_database(self):
        """Создание базы данных для хранения статусов"""
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

    def setup_google_sheets(self):
        """Настройка подключения к Google Sheets"""
        try:
            self.sheets_manager = GoogleSheetsManager()
            spreadsheet = self.sheets_manager.open_spreadsheet('Статусы Аниматоров')
            self.status_worksheet = self.sheets_manager.create_or_get_worksheet(
                spreadsheet, 
                'Статусы'
            )
        except Exception as e:
            logger.error(f"Ошибка настройки Google Sheets: {e}")
            self.status_worksheet = None

    def save_status(self, user_id: int, username: str, status: str):
        """Сохранение статуса в базу данных и Google Sheets"""
        conn = sqlite3.connect(self.DATABASE_PATH)
        cursor = conn.cursor()
        timestamp = datetime.now()
        
        # Сохранение в SQLite
        cursor.execute('''
            INSERT INTO statuses (user_id, username, status, timestamp) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, status, timestamp))
        conn.commit()
        conn.close()

        # Сохранение в Google Sheets
        if self.status_worksheet:
            self.sheets_manager.add_status_entry(
                self.status_worksheet, 
                user_id, 
                username, 
                status
            )

    def extract_status(self, text: str) -> str:
        """Извлечение статуса из сообщения"""
        for status in self.VALID_STATUSES:
            if status.lower() in text.lower():
                return status
        return None

    def create_telegram_app(self):
        """Создание Telegram приложения"""
        self.app = Application.builder().token(self.TOKEN).build()
        
        # Регистрация обработчиков
        self.app.add_handler(CommandHandler('start', self.start_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        return self.app

    async def start_command(self, update: Update, context):
        """Обработка команды /start"""
        await update.message.reply_text(
            "Привет! Я бот для отслеживания статусов аниматоров. "
            "Отправь мне статус: 'в пути', 'на месте' или 'закончил'."
        )

    async def handle_message(self, update: Update, context):
        """Обработка входящих сообщений"""
        user = update.effective_user
        text = update.message.text

        status = self.extract_status(text)
        if status:
            self.save_status(user.id, user.username or user.first_name, status)
            await update.message.reply_text(f"Статус '{status}' сохранен.")

    def create_app(self):
        """Создание Flask приложения для вебхука"""
        app = Flask(__name__)

        @app.route(f'/{self.TOKEN}', methods=['POST'])
        def webhook():
            """Обработчик webhook"""
            json_update = request.get_json(force=True)
            update = Update.de_json(json_update, Bot(self.TOKEN))
            
            try:
                # Создаем цикл событий и запускаем обработку
                import asyncio
                asyncio.run(self.app.process_update(update))
                return 'OK', 200
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return 'Error', 500

        # Создаем Telegram приложение при инициализации Flask-приложения
        self.create_telegram_app()
        
        return app

# Фабрика приложений для Render
def create_app():
    bot = AnimatorStatusBot()
    return bot.create_app()

# Точка входа для локального запуска
def main():
    bot = AnimatorStatusBot()
    app = bot.create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

if __name__ == '__main__':
    main()
