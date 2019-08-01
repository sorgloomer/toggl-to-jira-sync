start /min cmd /C scripts\open-page.bat
set FLASK_DEBUG=1
set APP_CONFIG_FILE=config/run.py
venv\Scripts\flask run --with-threads
