from bot import main  # импортируем функцию main из bot/main.py

def handler(event, context):
    return main(event)
