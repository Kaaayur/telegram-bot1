# Файл: bot/google_sheets.py

import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
import asyncio
import functools

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self, credentials_path=None):
        """Инициализация менеджера Google Sheets"""
        self.client = None
        self.spreadsheet = None
        self.worksheet = None

        try:
            if not credentials_path:
                try:
                    from bot.config import Config
                    credentials_path = Config.GOOGLE_SHEETS_CREDENTIALS_JSON
                    logger.warning("Используется путь к credentials из Config. Убедитесь, что это ПУТЬ к файлу.")
                except ImportError:
                    logger.error("Не удалось импортировать Config для получения пути к credentials.")
                    raise ValueError("Путь к credentials не указан и Config не найден.")
                except AttributeError:
                    logger.error("В Config не найден атрибут GOOGLE_SHEETS_CREDENTIALS_JSON")
                    raise ValueError("Атрибут GOOGLE_SHEETS_CREDENTIALS_JSON не найден в Config")

            scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

            if not os.path.exists(credentials_path):
                logger.error(f"Файл credentials не найден по указанному пути: {credentials_path}")
                return

            logger.info(f"Используется файл credentials: {credentials_path}")
            creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
            self.client = gspread.authorize(creds)
            logger.info("Клиент gspread успешно инициализирован.")

        except FileNotFoundError as fnf_err:
             logger.error(f"Ошибка инициализации Google Sheets (файл не найден): {fnf_err}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка инициализации Google Sheets: {e}", exc_info=True)


    def open_spreadsheet(self, spreadsheet_name):
        """Открытие Google Sheets по имени"""
        if not self.client:
             logger.error("Невозможно открыть таблицу: клиент gspread не инициализирован.")
             return None
        try:
            spreadsheet = self.client.open(spreadsheet_name)
            logger.info(f"Таблица '{spreadsheet_name}' успешно открыта.")
            self.spreadsheet = spreadsheet
            return spreadsheet
        except gspread.SpreadsheetNotFound:
            logger.error(f"Таблица '{spreadsheet_name}' не найдена.")
            return None
        except Exception as e:
             logger.error(f"Ошибка при открытии таблицы '{spreadsheet_name}': {e}", exc_info=True)
             return None

    def create_or_get_worksheet(self, spreadsheet, worksheet_name):
        """Создание или получение листа в таблице и сохранение его в self.worksheet"""
        if not spreadsheet:
             logger.error("Невозможно получить/создать лист: объект таблицы не предоставлен.")
             return None

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            logger.info(f"Рабочий лист '{worksheet_name}' найден.")
            self.worksheet = worksheet

        except gspread.WorksheetNotFound:
            logger.info(f"Рабочий лист '{worksheet_name}' не найден, попытка создания...")
            try:
                worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
                logger.info(f"Рабочий лист '{worksheet_name}' успешно создан.")
                self.worksheet = worksheet

                # Устанавливаем правильные заголовки
                headers = ['Дата', 'Имя артиста', 'Статус', 'Время']
                self.worksheet.append_row(headers, value_input_option='USER_ENTERED')
                logger.info(f"Заголовки {headers} добавлены в лист '{worksheet_name}'.")

            except Exception as e_add:
                logger.error(f"Ошибка создания нового листа '{worksheet_name}': {e_add}", exc_info=True)
                self.worksheet = None

        except Exception as e_get:
            logger.error(f"Ошибка получения листа '{worksheet_name}': {e_get}", exc_info=True)
            self.worksheet = None

        return self.worksheet

    async def add_status_entry(self, real_artist_name, status, timestamp_str):
        """
        Асинхронно добавляет запись в Google Sheets: Дата, Имя артиста, Статус, Время.
        """
        if not self.worksheet:
            logger.error("Попытка добавления записи, но рабочий лист (self.worksheet) не инициализирован.")
            return

        try:
            # Парсим переданную строку времени
            try:
                ts_datetime = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                date_str = ts_datetime.strftime('%d.%m.%Y') # Формат даты
                time_str = ts_datetime.strftime('%H:%M:%S') # Формат времени
            except ValueError:
                logger.warning(f"Не удалось распарсить timestamp_str '{timestamp_str}'. Используется текущее время.")
                current_time = datetime.now()
                date_str = current_time.strftime('%d.%m.%Y')
                time_str = current_time.strftime('%H:%M:%S')

            # Формируем строку данных для таблицы в нужном порядке
            row_data = [
                date_str,           # Дата
                real_artist_name,   # Имя артиста (переданное из main.py)
                status,             # Статус
                time_str            # Время
            ]

            loop = asyncio.get_running_loop()
            append_func_with_option = functools.partial(
                self.worksheet.append_row,
                value_input_option='USER_ENTERED'
            )
            await loop.run_in_executor(
                None,
                append_func_with_option,
                row_data
            )
            logger.info(f"Запись для '{real_artist_name}' успешно добавлена в Google Sheets.")

        except AttributeError as ae:
             logger.error(f"Ошибка атрибута при добавлении записи (self.worksheet={type(self.worksheet)}): {ae}", exc_info=True)
        except Exception as e:
            logger.error(f"Ошибка добавления записи в Google Sheets: {e}", exc_info=True)
