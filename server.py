import logging
import os.path
import sys

logging.basicConfig(level=logging.DEBUG)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from toggl_to_jira_sync import app

if __name__ == "__main__":
    app.main()
