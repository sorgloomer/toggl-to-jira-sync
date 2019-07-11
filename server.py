import argparse
import configparser
import datetime
import json
import os.path
from collections import OrderedDict

import flask
import pytz
import requests
from jinja2 import Undefined
from requests.auth import HTTPBasicAuth
from tzlocal import get_localzone

app = flask.Flask(__name__)


@app.template_filter("pretty_json")
def pretty_json(value):
    return json.dumps(value, sort_keys=True, indent=4, separators=(',', ': '))


@app.template_filter("repr")
def filter_repr(value):
    return repr(value)


@app.template_filter("local")
def filter_local(dt):
    if _not_defined(dt):
        return dt
    return dt.astimezone(get_localzone())


@app.template_filter("time")
def filter_time(dt):
    if _not_defined(dt):
        return dt
    return dt.time()


@app.template_filter("from_isoformat")
def filter_from_isoformat(s):
    if _not_defined(s):
        return s
    return from_isoformat(s)


def _not_defined(x):
    return x is None or x is Undefined


def get_secrets():
    secrets_path = os.path.join(os.path.dirname(__file__), "secrets.ini")
    if not os.path.isfile(secrets_path):
        return None
    secrets = configparser.ConfigParser()
    secrets.read(secrets_path)
    return Secrets(secrets)


class Secrets(object):
    def __init__(self, config):
        self.toggl_apitoken = config.get("secrets", "toggl.apitoken")
        self.toggl_workspace_name = config.get("config", "toggl.workspace.name")


def argparser():
    parser = argparse.ArgumentParser(description="Toggl to JIRA worklog sync")
    parser.add_argument("--debug", action="store_true", default=False)
    return parser


def parse_args():
    return argparser().parse_args()


class TogglApi(object):
    def __init__(self, secrets=None):
        if secrets is None:
            secrets = get_secrets()
        self.secrets = secrets
        self.api_base = "https://www.toggl.com/api"

    def _get(self, url, params=None):
        resp = requests.get(
            self.api_base + url,
            auth=HTTPBasicAuth(self.secrets.toggl_apitoken, "api_token"),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def get_projects(self, workspace_id):
        return self._get("/v8/workspaces/{workspace_id}/projects".format(workspace_id=workspace_id))

    def get_workspaces(self):
        return self._get("/v8/workspaces")

    def get_entries(self, start_datetime=None, end_datetime=None):
        params = {}
        if start_datetime is not None:
            params["start_date"] = to_isoformat(start_datetime)
        if end_datetime is not None:
            params["end_date"] = to_isoformat(end_datetime)
        return self._get("/v8/time_entries", params=params)


class DayBin(object):
    def __init__(self, localzone=None, turnpoint=None):
        if localzone is None:
            localzone = get_localzone()
        if turnpoint is None:
            turnpoint = datetime.timedelta(hours=6)
        self.localzone = localzone
        self.turnpoint = turnpoint

    def date_of(self, dt):
        return (dt.astimezone(self.localzone) - self.turnpoint).date()

    def start_datetime_of(self, d):
        return datetime.datetime.combine(d, datetime.time.min, tzinfo=self.localzone) + self.turnpoint

    def end_datetime_of(self, d):
        return self.start_datetime_of(d) + datetime.timedelta(days=1)


@app.route('/')
def index():
    day_bin = DayBin()
    secrets = get_secrets()
    toggl_api = TogglApi(secrets=secrets)
    today = day_bin.date_of(aware_now())

    if toggl_api.secrets is None:
        return flask.render_template("setup.html")
    workspaces = toggl_api.get_workspaces()
    workspace = _find(workspaces, name=secrets.toggl_workspace_name)
    projects = toggl_api.get_projects(workspace["id"])
    project_by_id = _index_by_id(projects)
    entries = toggl_api.get_entries(
        day_bin.start_datetime_of(today) - datetime.timedelta(days=7),
        day_bin.end_datetime_of(today)
    )
    return flask.render_template(
        "index.html",
        days=_into_bins(entries, lambda e: day_bin.date_of(from_isoformat(e['start'])), sorting='desc'),
        entries=entries,
        projects=projects,
        project_by_id=project_by_id,
        workspaces=workspaces,
    )


def _find(items, **filters):
    for item in items:
        if _matches(item, filters):
            return item
    return None


def _into_bins(items, key, sorting='asc') -> object:
    indexed = _group_by(items, key)
    result = [{"key": k, "values": v} for k, v in indexed.items()]
    if not sorting:
        return result
    return sorted(result, key=lambda i: i["key"], reverse=sorting == 'desc')


def _group_by_id(items):
    return _group_by(items, _id_of)


def _group_by(items, key):
    keyfn = _keyify(key)
    result = OrderedDict()
    for item in items:
        key_value = keyfn(item)
        bucket = result.get(key_value)
        if bucket is None:
            bucket = []
            result[key_value] = bucket
        bucket.append(item)
    return result


def _index_by_id(items):
    return _index_by(items, _id_of)


def _id_of(x):
    return x['id']


def _index_by(items, key):
    keyfn = _keyify(key)
    result = OrderedDict()
    for item in items:
        key_value = keyfn(item)
        result[key_value] = item
    return result


def _keyify(key):
    if isinstance(key, str):
        return lambda obj: obj[key]
    return key


def _matches(haystack, needles):
    return all(haystack.get(k) == v for k, v in needles.items())


def aware_now():
    return datetime.datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(get_localzone())


def to_isoformat(dt):
    if dt is None:
        return None
    return dt.isoformat(timespec='seconds')


def from_isoformat(s):
    if s is None:
        return None
    return datetime.datetime.fromisoformat(s)


def main():
    args = parse_args()
    app.run(debug=args.debug)


if __name__ == '__main__':
    main()
