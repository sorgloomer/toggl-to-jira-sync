import argparse
import configparser
import os.path


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


def argparser():
    parser = argparse.ArgumentParser(description="Toggl to JIRA worklog sync")
    parser.add_argument("--debug", action="store_true", default=False)
    return parser


def parse_args():
    return argparser().parse_args()
