#!/bin/bash
gunicorn --worker-tmp-dir /dev/shm -w 4 -b 0.0.0.0:$PORT -k uvicorn.workers.UvicornWorker "bot.main:flask_app"
