#!/bin/bash
gunicorn --worker-tmp-dir /dev/shm -w 4 -b 0.0.0.0:$PORT "bot.main:flask_app()"
