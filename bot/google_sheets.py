# В файле bot/google_sheets.py
import os
import gspread
# Используем старую библиотеку, раз она у вас есть
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
import asyncio # <-- Добавлено

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    def __init__(self, credentials_path=None):
        """Инициализация менеджера Google Sheets"""
        self.client = None
        self.spreadsheet = None
        self.worksheet = None # <--- Инициализируем атрибут для хранения листа

        try:
            # Определение пути к credentials (логика оставлена как есть)
            if not credentials_path:
                # Попытка импортировать Config здесь может быть не лучшей идеей,
                # лучше передавать путь явно при создании GoogleSheetsManager.
                # Но оставим пока так, если это работает для вас.
                try:
                    from bot.config import Config
                    credentials_path = Config.GOOGLE_SHEETS_CREDENTIALS_JSON # Убедитесь, что это ПУТЬ, а не сам JSON
                    logger.warning("Получение пути credentials из Config - убедитесь, что Config.GOOGLE_SHEETS_CREDENTIALS_JSON содержит ПУТЬ к файлу.")
                except ImportError:
                    logger.error("Не удалось импортировать Config для получения пути к credentials.")
                    raise ValueError("Путь к credentials не указан и Config не найден.")


            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            # Проверка существования файла credentials
            if not os.path.exists(credentials_path):
                logger.error(f"Файл credentials не найден: {credentials_path}")
                # Не бросаем исключение сразу, а устанавливаем client в None
                # raise FileNotFoundError(f"Файл {credentials_path} не найден")
                return # Завершаем инициализацию, self.client останется None

            # Аутентификация
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                credentials_path,
                scope
            )

            self.client = gspread.authorize(creds)
            logger.info("Клиент gspread успешно инициализирован.")

        except FileNotFoundError as fnf_err:
             # Ловим ошибку отсутствия файла credentials явно
             logger.error(f"Ошибка инициализации Google Sheets: {fnf_err}")
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
            # Сохраняем ссылку на таблицу, может пригодиться
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
                    cols=10    # Начальное количество колонок
                )
                logger.info(f"Рабочий лист '{worksheet_name}' успешно создан.")
                # Сохраняем созданный лист
                self.worksheet = worksheet # <--- Сохраняем объект листа

                # Инициализация заголовков (добавляем User ID)
                headers = ['User ID', 'Дата', 'Артист', 'Статус', 'Время']
                # Выполняем синхронно, так как это часть инициализации
                self.worksheet.append_row(headers, value_input_option='USER_ENTERED')
                logger.info(f"Заголовки добавлены в лист '{worksheet_name}'.")

            except Exception as e_add:
                logger.error(f"Ошибка создания нового листа '{worksheet_name}': {e_add}", exc_info=True)
                self.worksheet = None # Сбрасываем, если создание не удалось

        except Exception as e_get:
            logger.error(f"Ошибка получения листа '{worksheet_name}': {e_get}", exc_info=True)
            self.worksheet = None # Сбрасываем, если получение не удалось

        # Возвращаем сохраненный объект листа (или None, если не удалось)
        return self.worksheet

    # ИЗМЕНЕНО: async def и аргументы
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
            # Пытаемся распарсить переданную строку времени обратно в datetime,
            # чтобы извлечь дату и время отдельно, как в оригинальном коде.
            # Если формат всегда '%Y-%m-%d %H:%M:%S', это сработает.
            try:
                ts_datetime = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                date_str = ts_datetime.strftime('%d.%m.%Y')
                time_str = ts_datetime.strftime('%H:%M:%S')
            except ValueError:
                # Если парсинг не удался, используем строку как есть или текущее время
                logger.warning(f"Не удалось распарсить timestamp_str '{timestamp_str}', используем как есть и текущее время.")
                # В качестве запасного варианта можно использовать всю строку или текущую дату/время
                current_time = datetime.now()
                date_str = current_time.strftime('%d.%m.%Y')
                time_str = current_time.strftime('%H:%M:%S')
                # Или можно просто использовать timestamp_str для одного из полей

            # Формируем строку данных, включая user_id
            row_data = [
                user_id,                           # User ID (новый столбец)
                date_str,                          # Дата
                username or f'ID:{user_id}',       # Артист (добавили ID как fallback)
                status,                            # Статус
                time_str                           # Время
            ]

            # Получаем текущий event loop
            loop = asyncio.get_running_loop()

            # Выполняем блокирующий вызов append_row в отдельном потоке
            await loop.run_in_executor(
                None,                              # Использовать executor по умолчанию (ThreadPoolExecutor)
                self.worksheet.append_row,         # Метод, который нужно выполнить
                row_data,                          # Аргументы для метода append_row
                {'value_input_option': 'USER_ENTERED'} # Доп. параметры для append_row
            )

            logger.info(f"Запись для {username} ({user_id}) успешно добавлена в Google Sheets.")

        except AttributeError as ae:
             # Эта ошибка означает, что self.worksheet - не объект gspread Worksheet
             logger.error(f"Ошибка атрибута при добавлении записи (ожидался объект Worksheet, но self.worksheet={type(self.worksheet)}): {ae}", exc_info=True)
        except Exception as e:
            logger.error(f"Ошибка добавления записи в Google Sheets: {e}", exc_info=True)
