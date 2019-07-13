import os.path
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from toggl_to_jira_sync import app

if __name__ == "__main__":
    app.main()
