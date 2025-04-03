# Файл: bot/google_sheets.py

import os
import gspread
# Используем старую библиотеку, раз она у вас есть
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
import asyncio
import functools # <-- Добавлен импорт

logger = logging.getLogger(__name__) # Используем имя модуля для логгера

class GoogleSheetsManager:
    def __init__(self, credentials_path=None):
        """Инициализация менеджера Google Sheets"""
        self.client = None
        self.spreadsheet = None
        self.worksheet = None # <--- Инициализируем атрибут для хранения листа

        try:
            # Определение пути к credentials
            # TODO: Желательно передавать путь явно, а не импортировать Config здесь
            if not credentials_path:
                try:
                    from bot.config import Config
                    # УБЕДИТЕСЬ, ЧТО ЗДЕСЬ ХРАНИТСЯ ПУТЬ К ФАЙЛУ, А НЕ JSON-СТРОКА
                    credentials_path = Config.GOOGLE_SHEETS_CREDENTIALS_JSON
                    logger.warning("Используется путь к credentials из Config. Убедитесь, что Config.GOOGLE_SHEETS_CREDENTIALS_JSON - это ПУТЬ.")
                except ImportError:
                    logger.error("Не удалось импортировать Config для получения пути к credentials.")
                    raise ValueError("Путь к credentials не указан и Config не найден.")
                except AttributeError:
                    logger.error("В Config не найден атрибут GOOGLE_SHEETS_CREDENTIALS_JSON")
                    raise ValueError("Атрибут GOOGLE_SHEETS_CREDENTIALS_JSON не найден в Config")


            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            # Проверка существования файла credentials
            if not os.path.exists(credentials_path):
                logger.error(f"Файл credentials не найден по указанному пути: {credentials_path}")
                # Не бросаем исключение, а просто завершаем инициализацию
                return # self.client останется None

            logger.info(f"Используется файл credentials: {credentials_path}")
            # Аутентификация
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path,
                scope
            )

            self.client = gspread.authorize(creds)
            logger.info("Клиент gspread успешно инициализирован.")

        except FileNotFoundError as fnf_err:
             # Ловим ошибку отсутствия файла credentials явно
             logger.error(f"Ошибка инициализации Google Sheets (файл не найден): {fnf_err}")
             # self.client останется None
        except Exception as e:
            logger.error(f"Неожиданная ошибка инициализации Google Sheets: {e}", exc_info=True)
            # self.client останется None


    def open_spreadsheet(self, spreadsheet_name):
        """Открытие Google Sheets по имени"""
        if not self.client:
             logger.error("Невозможно открыть таблицу: клиент gspread не инициализирован.")
             return None
        try:
            spreadsheet = self.client.open(spreadsheet_name)
            logger.info(f"Таблица '{spreadsheet_name}' успешно открыта.")
            # Сохраняем ссылку на таблицу
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
            # Попытка получить существующий лист
            worksheet = spreadsheet.worksheet(worksheet_name)
            logger.info(f"Рабочий лист '{worksheet_name}' найден.")
            # Сохраняем найденный лист
            self.worksheet = worksheet # <--- Сохраняем объект листа

        except gspread.WorksheetNotFound:
            logger.info(f"Рабочий лист '{worksheet_name}' не найден, попытка создания...")
            try:
                # Создание нового листа
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name,
                    rows=1000, # Начальное количество строк
                    cols=10    # Начальное количество колонок (достаточно для 5 столбцов)
                )
                logger.info(f"Рабочий лист '{worksheet_name}' успешно создан.")
                # Сохраняем созданный лист
                self.worksheet = worksheet # <--- Сохраняем объект листа

                # Инициализация заголовков (User ID, Дата, Артист, Статус, Время)
                headers = ['User ID', 'Дата', 'Артист', 'Статус', 'Время']
                # Выполняем синхронно, так как это часть инициализации
                # Используем value_input_option='USER_ENTERED' для правильного форматирования
                self.worksheet.append_row(headers, value_input_option='USER_ENTERED')
                logger.info(f"Заголовки {headers} добавлены в лист '{worksheet_name}'.")

            except Exception as e_add:
                logger.error(f"Ошибка создания нового листа '{worksheet_name}': {e_add}", exc_info=True)
                self.worksheet = None # Сбрасываем, если создание не удалось

        except Exception as e_get:
            logger.error(f"Ошибка получения листа '{worksheet_name}': {e_get}", exc_info=True)
            self.worksheet = None # Сбрасываем, если получение не удалось

        # Возвращаем сохраненный объект листа (или None, если не удалось)
        return self.worksheet

    async def add_status_entry(self, user_id, username, status, timestamp_str):
        """
        Асинхронно добавляет запись о статусе в Google Sheets,
        используя сохраненный self.worksheet.
        """
        # Проверяем, был ли лист успешно инициализирован и сохранен
        if not self.worksheet:
            logger.error("Попытка добавления записи, но рабочий лист (self.worksheet) не инициализирован.")
            return # Не можем продолжить

        try:
            # Парсим переданную строку времени
            try:
                ts_datetime = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                date_str = ts_datetime.strftime('%d.%m.%Y') # Формат даты как в оригинале
                time_str = ts_datetime.strftime('%H:%M:%S') # Формат времени как в оригинале
            except ValueError:
                # Если парсинг не удался, используем запасной вариант
                logger.warning(f"Не удалось распарсить timestamp_str '{timestamp_str}'. Используется текущее время.")
                current_time = datetime.now()
                date_str = current_time.strftime('%d.%m.%Y')
                time_str = current_time.strftime('%H:%M:%S')

            # Формируем строку данных для таблицы
            row_data = [
                user_id,                           # User ID
                date_str,                          # Дата
                username or f'ID:{user_id}',       # Артист (с fallback на ID)
                status,                            # Статус
                time_str                           # Время
            ]

            # Получаем текущий event loop
            loop = asyncio.get_running_loop()

            # Создаем частичную функцию для append_row с нужными keyword аргументами
            append_func_with_option = functools.partial(
                self.worksheet.append_row,
                value_input_option='USER_ENTERED' # Передаем как именованный аргумент
            )

            # Выполняем блокирующий вызов gspread в отдельном потоке
            await loop.run_in_executor(
                None,                       # Использовать executor по умолчанию
                append_func_with_option,    # Вызываем partial функцию
                row_data                    # Передаем данные как позиционный аргумент
            )

            logger.info(f"Запись для {username} ({user_id}) успешно добавлена в Google Sheets.")

        except AttributeError as ae:
             # Ошибка, если self.worksheet не является ожидаемым объектом
             logger.error(f"Ошибка атрибута при добавлении записи (self.worksheet={type(self.worksheet)}): {ae}", exc_info=True)
        except Exception as e:
            # Ловим другие возможные ошибки gspread или asyncio
            logger.error(f"Ошибка добавления записи в Google Sheets: {e}", exc_info=True)
