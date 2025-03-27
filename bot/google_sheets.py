import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self, credentials_path=None):
        """Инициализация менеджера Google Sheets"""
        try:
            # Определение пути к credentials
            if not credentials_path:
                from bot.config import Config
                credentials_path = Config.GOOGLE_CREDENTIALS_PATH

            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Проверка существования файла credentials
            if not os.path.exists(credentials_path):
                logger.error(f"Файл credentials не найден: {credentials_path}")
                raise FileNotFoundError(f"Файл {credentials_path} не найден")
            
            # Аутентификация
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path, 
                scope
            )
            
            self.client = gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}")
            raise

    def open_spreadsheet(self, spreadsheet_name):
        """Открытие Google Sheets по имени"""
        try:
            spreadsheet = self.client.open(spreadsheet_name)
            return spreadsheet
        except gspread.SpreadsheetNotFound:
            logger.error(f"Таблица {spreadsheet_name} не найдена")
            return None

    def create_or_get_worksheet(self, spreadsheet, worksheet_name):
        """Создание или получение листа в таблице"""
        try:
            # Попытка получить существующий лист
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            # Создание нового листа
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, 
                rows=1000, 
                cols=10
            )
            
            # Инициализация заголовков
            headers = ['Дата', 'Артист', 'Статус', 'Время']
            worksheet.append_row(headers)
        
        return worksheet

    def add_status_entry(self, worksheet, user_id, username, status):
        """Добавление записи о статусе в Google Sheets"""
        try:
            current_time = datetime.now()
            row_data = [
                current_time.strftime('%d.%m.%Y'),  # Дата
                username or 'Без имени',            # Артист
                status,                             # Статус
                current_time.strftime('%H:%M:%S')   # Время
            ]
            
            worksheet.append_row(row_data)
            logger.info(f"Запись добавлена для {username}: {status}")
        except Exception as e:
            logger.error(f"Ошибка добавления записи: {e}")
