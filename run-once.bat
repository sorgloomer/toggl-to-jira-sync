call venv\Scripts\activate.bat
start /min cmd /C scripts\open-page.bat
set APP_CONFIG_FILE=config/run.py
flask run --with-threads
