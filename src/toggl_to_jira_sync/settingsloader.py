import argparse
import json
from collections import OrderedDict


def get_secrets():
    return Secrets(_load_json("secrets.json"))


def get_settings():
    return Settings(_load_json("settings.json"))


def _load_json(filename):
    with open(filename, encoding="utf-8") as f:
        return json.load(f)


class Secrets(object):
    def __init__(self, secrets):
        self.toggl_apitoken = secrets["toggl.apitoken"]
        self.jira_username = secrets["jira.username"]
        self.jira_password = secrets["jira.password"]


class Settings(object):
    def __init__(self, settings):
        self.toggl_workspace_name = settings["toggl.workspace.name"]
        self.jira_url_base = settings["jira.url_base"]
        self.projects = {
            k: ProjectSettings(v)
            for k, v in settings["projects"].items()
        }


class ProjectSettings(object):
    def __init__(self, p):
        self.toggl_project = p.get("toggl.project", None)
        self.toggl_billable = p.get("toggl.billable", True)
        self.jira_skip = p.get("jira.skip", False)


def argparser():
    parser = argparse.ArgumentParser(description="Toggl to JIRA worklog sync")
    parser.add_argument("--debug", action="store_true", default=False)
    return parser


def parse_args():
    return argparser().parse_args()


def _get_config_dict(config, section, prefix):
    result = OrderedDict()
    for k, v in config.items(section):
        if k.startswith(prefix):
            result[k[len(prefix):]] = v
    return result


def _get_config_array(config, section, key):
    value = config.get(section, key, fallback="")
    return value.split(",") if value else []
