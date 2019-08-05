#!/usr/bin/env sh
source venv/bin/activate.sh
export APP_CONFIG_FILE=config/run.py
sh scripts/open-page.sh &
flask run --with-threads
