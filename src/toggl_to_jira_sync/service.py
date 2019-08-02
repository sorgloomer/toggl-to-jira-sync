import datetime
from collections import namedtuple

import pytz
from requests.auth import HTTPBasicAuth
from tzlocal import get_localzone

from toggl_to_jira_sync import settingsloader
from toggl_to_jira_sync.apis import JiraApi, TogglApi


def create_jira_api(secrets=None, settings=None):
    if secrets is None:
        secrets = settingsloader.get_secrets()
    if settings is None:
        settings = settingsloader.get_settings()
    return JiraApi(
        api_base=settings.jira_url_base,
        auth=HTTPBasicAuth(username=secrets.jira_username, password=secrets.jira_password)
    )


def aware_now():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(get_localzone())


SecretsAndApis = namedtuple("SecretsAndApis", ["toggl", "jira", "secrets", "settings"])


def get_apis(secrets=None, settings=None):
    if secrets is None:
        secrets = settingsloader.get_secrets()
    if settings is None:
        settings = settingsloader.get_settings()
    toggl_api = TogglApi(secrets=secrets)
    jira_api = create_jira_api(secrets=secrets, settings=settings)
    return SecretsAndApis(
        toggl=toggl_api,
        jira=jira_api,
        secrets=secrets,
        settings=settings,
    )


class ActionExecutor(object):
    def __init__(self, apis=None):
        if apis is None:
            apis = get_apis()
        self.apis = apis

    def execute(self, action):
        action["result"] = getattr(self, "_action_{type}_{action}".format(**action))(action)

    def _action_toggl_update(self, action):
        self.apis.toggl.update(action["id"], action["values"])

    def _action_jira_create(self, action):
        self.apis.jira.add_entry(action["issue"], action["values"])

    def _action_jira_delete(self, action):
        self.apis.jira.delete_entry(action["issue"], action["id"])

    def _action_jira_update(self, action):
        self.apis.jira.update_entry(action["issue"], action["id"], action["values"])
