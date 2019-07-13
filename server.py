import argparse
import configparser
import datetime
import functools
import json
import math
import os.path
import pprint
from collections import OrderedDict, namedtuple

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
    return datetime_toggl_format.from_str(s)


@app.template_filter("pformat")
def filter_pformat(x):
    if _not_defined(x):
        return x
    return pprint.pformat(x)


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
        self.jira_username = config.get("secrets", "jira.username")
        self.jira_password = config.get("secrets", "jira.password")
        self.jira_url_base = config.get("config", "jira.url_base")


def argparser():
    parser = argparse.ArgumentParser(description="Toggl to JIRA worklog sync")
    parser.add_argument("--debug", action="store_true", default=False)
    return parser


def parse_args():
    return argparser().parse_args()


def transform_result(transform_fn):
    @decorator
    def _transform_result(target):
        return transform_fn(target())
    return _transform_result


def decorator(decorator_func):
    @functools.wraps(decorator_func)
    def _decorator(func):
        @functools.wraps(func)
        def _decorator_wrapper(*args, **kwargs):
            return decorator_func(InvocationTarget(func, args, kwargs))
        return _decorator_wrapper
    return _decorator


class InvocationTarget:
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def forward(self):
        print(self.func, self.args, self.kwargs)
        return self.func(*self.args, **self.kwargs)

    def __call__(self):
        return self.forward()


class TogglApi(object):
    def __init__(self, secrets=None):
        if secrets is None:
            secrets = get_secrets()
        self.secrets = secrets
        self.api_base = "https://www.toggl.com/api/"

    def _get(self, url, params=None):
        resp = requests.get(
            self.api_base + url,
            auth=HTTPBasicAuth(self.secrets.toggl_apitoken, "api_token"),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def get_projects(self, workspace_id):
        return self._get("v8/workspaces/{workspace_id}/projects".format(workspace_id=workspace_id))

    def get_workspaces(self):
        return self._get("v8/workspaces")

    def get_entries(self, start_datetime=None, end_datetime=None):
        params = {}
        if start_datetime is not None:
            params["start_date"] = datetime_toggl_format.to_str(start_datetime)
        if end_datetime is not None:
            params["end_date"] = datetime_toggl_format.to_str(end_datetime)
        return self._get("v8/time_entries", params=params)

    @transform_result(list)
    def get_worklog(self, workspace_name, min_datetime=None, max_datetime=None):
        workspaces = self.get_workspaces()
        workspace = _find(workspaces, name=workspace_name)
        projects = self.get_projects(workspace["id"])
        project_by_id = _index_by_id(projects)
        entries = self.get_entries(start_datetime=min_datetime, end_datetime=max_datetime)
        assert len(set(e["uid"] for e in entries)) <= 1
        pprint.pprint(entries)
        for entry in entries:
            project = project_by_id.get(entry.get("pid"))
            yield self._extract_entry(entry, project)

    @classmethod
    def _extract_entry(cls, entry, project):
        description = entry["description"]
        return WorklogEntry(
            issue=cls._extract_issue(description),
            start=datetime_toggl_format.from_str(entry["start"]),
            stop=datetime_toggl_format.from_str(entry["stop"]),
            comment=description,
            tag=TogglTag(
                id=entry["id"],
                project=project["name"] if project is not None else None,
                billable=entry["billable"],
            ),
        )

    @staticmethod
    def _extract_issue(description):
        return _strip_after_any(description.strip(), (":", " ")).strip()


def _strip_after_any(haystack, needles):
    for needle in needles:
        haystack = haystack.split(needle, 1)[0]
    return haystack


JiraWorklogFilter = namedtuple("JiraWorklogFilter", ["author", "min_date", "max_date"])


class JiraApi(object):
    def __init__(self, api_base, auth=None):
        self.api_base = api_base
        self.session = requests.Session()
        self.session.auth = auth

    def get_worklog(self, author=None, min_datetime=None, max_datetime=None):
        worklog_filter = JiraWorklogFilter(author=author, min_date=min_datetime, max_date=max_datetime)
        jql = self._assemble_jql(worklog_filter, date_error_margin=datetime.timedelta(days=1))
        resp = self.execute_jql(jql)
        return self._get_filtered_worklogs(resp, worklog_filter)

    def execute_jql(self, jql):
        return self._get("rest/api/2/search", params={"jql": jql})

    def _get_filtered_worklogs(self, resp, worklog_filter):
        return [
            worklog_item
            for issue in resp["issues"]
            for worklog_item in self._fetch_worklog(worklog_filter, issue)
        ]

    def _get(self, url, params=None):
        resp = self.session.get(
            self.api_base + url,
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _assemble_jql(worklog_filter, date_error_margin=None):
        if date_error_margin is None:
            date_error_margin = datetime.timedelta()
        filters = []
        if worklog_filter.author is not None:
            filters.append('worklogAuthor = "{value}"'.format(
                value=worklog_filter.author
            ))
        if worklog_filter.min_date is not None:
            filters.append('worklogDate >= "{value}"'.format(
                value=datetime_jira_date_format.to_str(worklog_filter.min_date - date_error_margin)
            ))
        if worklog_filter.max_date is not None:
            filters.append('worklogDate <= "{value}"'.format(
                value=datetime_jira_date_format.to_str(worklog_filter.max_date + date_error_margin)
            ))
        return " AND ".join(filters)

    def _fetch_worklog(self, worklog_filter, issue):
        resp = self._get("rest/api/2/issue/{key}/worklog".format(key=issue["key"]))
        for worklog in resp["worklogs"]:
            if self._worklog_matches_filter(worklog, worklog_filter):
                started = datetime_jira_format.from_str(worklog["started"])
                ended = started + datetime.timedelta(seconds=worklog["timeSpentSeconds"])
                yield WorklogEntry(
                    issue=issue["key"],
                    start=started,
                    stop=ended,
                    comment=worklog["comment"],
                    tag=JiraTag(id=worklog["id"]),
                )

    @staticmethod
    def _worklog_matches_filter(worklog_entry_dto, worklog_filter):
        if worklog_filter.author not in [worklog_entry_dto["author"]["key"], worklog_entry_dto["author"]["name"]]:
            return False
        started = datetime_jira_format.from_str(worklog_entry_dto["started"])
        if worklog_filter.min_date is not None and started < worklog_filter.min_date:
            return False
        if worklog_filter.max_date is not None and started > worklog_filter.max_date:
            return False
        return True


WorklogEntry = namedtuple("WorklogEntry", [
    "issue",
    "start",
    "stop",
    "comment",
    "tag",
])

JiraTag = namedtuple("JiraTag", ["id"])
TogglTag = namedtuple("TogglTag", ["id", "project", "billable"])


def _pairing_order(pairing):
    toggl_entry, jira_entry, dist = pairing
    if toggl_entry is not None:
        return toggl_entry.start
    if jira_entry is not None:
        return jira_entry.start
    return None


def calculate_pairing(toggl_logs, jira_logs):
    return sorted(
        _calculate_pairing(toggl_logs, jira_logs, worklog_entry_distance, 5),
        key=_pairing_order
    )


def _calculate_pairing(xs, ys, distfn, threshold):
    xs = OrderedDict(enumerate(xs))
    ys = OrderedDict(enumerate(ys))
    dists = sorted(
        (distfn(xvalue, yvalue), xid, yid)
        for xid, xvalue in xs.items()
        for yid, yvalue in ys.items()
    )
    for dist, xid, yid in dists:
        if dist > threshold:
            break
        if xid in xs and yid in ys:
            yield (xs.pop(xid), ys.pop(yid), dist)
    for x in xs.values():
        yield (x, None, None)
    for y in ys.values():
        yield (None, y, None)


def worklog_entry_distance(a, b):
    return (
        + 4 * _worklog_str_dist(a.issue, b.issue)
        + 1 * _worklog_str_dist(a.comment, b.comment)
        + 2 * _worklog_datetime_dist(a.start, b.start)
        + 1 * _worklog_datetime_dist(a.stop, b.stop)
    )


def _worklog_str_dist(x, y):
    return 0 if x == y else 1


def _worklog_datetime_dist(dt1, dt2):
    return abs(dt1 - dt2) / datetime.timedelta(minutes=60)


def create_jira_api(secrets=None):
    if secrets is None:
        secrets = get_secrets()
    return JiraApi(
        api_base=secrets.jira_url_base,
        auth=HTTPBasicAuth(username=secrets.jira_username, password=secrets.jira_password)
    )


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
    jira_api = create_jira_api(secrets)
    today = day_bin.date_of(aware_now())

    if toggl_api.secrets is None:
        return flask.render_template("setup.html")

    min_datetime = day_bin.start_datetime_of(today) - datetime.timedelta(days=7)
    max_datetime = day_bin.end_datetime_of(today)

    jira_worklog = jira_api.get_worklog(
        author=secrets.jira_username,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    toggl_worklog = toggl_api.get_worklog(
        workspace_name=secrets.toggl_workspace_name,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    pairing = calculate_pairing(toggl_worklog, jira_worklog)

    return flask.render_template(
        "index.html",
        days=_into_bins(toggl_worklog, lambda e: day_bin.date_of(e.start), sorting='desc'),
        jira_worklog=jira_worklog,
        toggl_worklog=toggl_worklog,
        pairing=pairing
    )


def _find(items, **filters):
    for item in items:
        if _matches(item, filters):
            return item
    return None


def _into_bins(items, key, sorting='asc') -> object:
    indexed = _group_by(items, key)
    result = list(indexed.items())
    if not sorting:
        return result
    return sorted(result, key=key_of_kv, reverse=sorting == 'desc')


def key_of_kv(kv):
    return kv[0]


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


class DatetimeTogglFormat:
    @staticmethod
    def to_str(dt):
        if dt is None:
            return None
        return dt.isoformat(timespec='seconds')

    @staticmethod
    def from_str(s):
        if s is None:
            return None
        return datetime.datetime.fromisoformat(s)


class DatetimeFormat:
    def __init__(self, format_str=None):
        if format_str is None:
            format_str = "%Y-%m-%d"
        self.format = format_str

    def to_str(self, dt):
        if dt is None:
            return None
        return dt.strftime(self.format)

    def from_str(self, s):
        if s is None:
            return None
        return datetime.datetime.strptime(s, self.format)


datetime_jira_date_format = DatetimeFormat("%Y-%m-%d")
datetime_jira_format = DatetimeFormat("%Y-%m-%dT%H:%M:%S.%f%z")
datetime_toggl_format = DatetimeTogglFormat()


def main():
    args = parse_args()
    app.run(debug=args.debug)


if __name__ == '__main__':
    main()
