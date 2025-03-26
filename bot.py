import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from google.oauth2 import service_account
import gspread
import config
import datetime

#  Для webhook'ов на PythonAnywhere
from aiohttp import web

# Настройки логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()

# Функция подключения к Google Sheets
def setup_gspread():
    """Настройка доступа к Google Sheets."""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, scopes=scope
        )
        client = gspread.authorize(creds)
        print("✅ Успешно подключился к Google API")
        return client
    except Exception as e:
        print(f"❌ Ошибка при подключении к Google API: {e}")
        print(f"   Подробности: {type(e).__name__}: {e}")
        return None

# ---- Команда /start ----
@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start."""
    if str(message.from_user.id) not in config.ANIMATOR_IDS:
        await message.answer("🚫 Вы не зарегистрированы как аниматор.")
        return
    await message.answer("Привет! Я бот для сбора статусов аниматоров.")


# ---- Обработка сообщений ----
@dp.message()
async def handle_message(message: Message):
    """Обработка входящих сообщений."""
    text = message.text.lower()
    user_id = str(message.from_user.id)
    chat_id = message.chat.id

    print(f"Обработано сообщение от пользователя {user_id} в группе {chat_id}: {text}")

    if chat_id != config.GROUP_CHAT_ID:
        print(f"⚠ Сообщение не из целевой группы (ID: {chat_id})")
        return

    if user_id not in config.ANIMATOR_IDS:
        print(f"⚠ Неизвестный пользователь: {user_id}")
        return

    for keyword in config.KEYWORDS:
        if keyword in text:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            animator_name = config.ANIMATOR_IDS[user_id]
            await log_to_google_sheets(animator_name, keyword, timestamp)
            await message.reply(f"✅ Статус '{keyword}' записан для пользователя {animator_name}.")
            break


# ---- Функция записи в Google Sheets ----
async def log_to_google_sheets(animator_name, status, timestamp):
    """Запись данных в Google таблицу."""
    print(f"✅ Запись данных для аниматора {animator_name}, статус: {status}, время: {timestamp}")
    client = setup_gspread()
    if not client:
        return

    sheet = client.open_by_key(config.SPREADSHEET_KEY).sheet1
    date_str = timestamp.split()[0]

    try:
        date_cell = sheet.find(date_str, in_column=1)
        date_row = date_cell.row
    except Exception:
        date_row = None

    try:
        artist_col = sheet.find("Артист").col
        status_col = sheet.find("Статус").col
        time_col = sheet.find("Время").col
    except Exception as e:
        print("❌ Ошибка: Не найдены заголовки столбцов ('Артист', 'Статус', 'Время')")
        print(f"   Подробности: {type(e).__name__}: {e}")
        return

    if date_row is not None:
        empty_row = date_row + 1
        while True:
            if not sheet.cell(empty_row, artist_col).value and \
               not sheet.cell(empty_row, status_col).value and \
               not sheet.cell(empty_row, time_col).value:
                break
            empty_row += 1

    else:
        empty_row = 2
        while True:
            cell_value = sheet.cell(empty_row, 1).value
            if cell_value is None or cell_value == "":
                break
            empty_row += 1
        sheet.insert_row([date_str], empty_row)
        empty_row += 1
        sheet.insert_row([], empty_row)

    try:
        sheet.update_cell(empty_row, artist_col, animator_name)
        sheet.update_cell(empty_row, status_col, status)
        sheet.update_cell(empty_row, time_col, timestamp.split(" ")[1])
        logger.info(f"✅ Записано: {animator_name}, {status}, {timestamp}")
    except Exception as e:
        print(f"❌ Ошибка при записи данных в таблицу.")
        print(f"   Подробности: {type(e).__name__}: {e}")


# ---- Webhook setup (aiohttp) ----

async def on_startup(app):
    """Действия при запуске приложения (нужно для установки вебхука)."""
    webhook_url = f"https://{config.PA_USERNAME}.pythonanywhere.com/webhook"
    await bot.set_webhook(webhook_url)
    print(f"✅ Webhook установлен на {webhook_url}")


async def on_shutdown(app):
    """Действия при остановке приложения."""
    await bot.delete_webhook()
    print("✅ Webhook удалён.")
    await dp.storage.close()

async def handle_webhook(request):
    """Обработчик вебхука."""
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response(text="OK")

# ---- PythonAnywhere-specific setup ----

def main():

    app = web.Application()
    app.router.add_post('/webhook', handle_webhook)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    return app