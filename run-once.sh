#!/usr/bin/env sh
export FLASK_DEBUG=1
export APP_CONFIG_FILE=config/run.py
sh scripts/open-page.sh &
venv/bin/flask run --with-threads
