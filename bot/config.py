import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

class Config:
    # Токен бота
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # URL webhook
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    
    # Путь к credentials Google Sheets
    GOOGLE_CREDENTIALS_PATH = os.getenv(
        'GOOGLE_CREDENTIALS_PATH', 
        'credentials.json'
    )
