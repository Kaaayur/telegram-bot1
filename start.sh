#!/bin/bash
uvicorn bot.main:asgi_app --host 0.0.0.0 --port $PORT --workers 4
