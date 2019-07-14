import argparse
import configparser
import os.path
from collections import OrderedDict


def get_secrets():
    secrets_path = "secrets.ini"
    if not os.path.isfile(secrets_path):
        return None
    secrets = configparser.ConfigParser()
    secrets.read(secrets_path)
    return Secrets(secrets)


class Secrets(object):
    def __init__(self, config):
        self.toggl_apitoken = config.get("secrets", "toggl.apitoken")
        self.toggl_workspace_name = config.get("config", "toggl.workspace.name")
        self.jira_username = config.get("secrets", "jira.username")
        self.jira_password = config.get("secrets", "jira.password")
        self.jira_url_base = config.get("config", "jira.url_base")
        self.toggl_projects = _get_config_dict(config, "config", "toggl.projects.")


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
