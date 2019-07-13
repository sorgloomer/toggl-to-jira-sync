import datetime

import pytz
from requests.auth import HTTPBasicAuth
from tzlocal import get_localzone

from toggl_to_jira_sync import config
from toggl_to_jira_sync.apis import JiraApi


def create_jira_api(secrets=None):
    if secrets is None:
        secrets = config.get_secrets()
    return JiraApi(
        api_base=secrets.jira_url_base,
        auth=HTTPBasicAuth(username=secrets.jira_username, password=secrets.jira_password)
    )


def aware_now():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(get_localzone())
