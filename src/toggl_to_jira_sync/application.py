import datetime
import json
import pprint

import flask
from jinja2 import Undefined
from markupsafe import Markup
from tzlocal import get_localzone
from werkzeug.urls import url_encode

from toggl_to_jira_sync import config, utils, actions
from toggl_to_jira_sync.apis import TogglApi
from toggl_to_jira_sync.core import DayBin, calculate_pairing
from toggl_to_jira_sync.formats import datetime_toggl_format
from toggl_to_jira_sync.service import create_jira_api, aware_now

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


@app.template_filter("format_datetime")
def filter_format_datetime(dt, format_str):
    if _not_defined(dt):
        return dt
    return dt.strftime(format_str)


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


@app.template_filter("pre")
def filter_pre(x):
    if _not_defined(x):
        return x
    if isinstance(x, Markup):
        x = x.unescape()
    lines = []
    for line in x.split("\n"):
        line = (flask.escape(line)
                     .replace(" ", Markup("&nbsp;"))
                     .replace("\t", Markup("&nbsp;" * 4))
                )
        lines.extend([Markup("<div>"), line, Markup("</div>\n")])
    return Markup().join(lines)


@app.template_global()
def modify_query(**kwargs):
    params = dict()
    params.update(flask.request.args)
    _update_allowing_pop(params, kwargs)
    if not params:
        return flask.request.path
    return '{}?{}'.format(flask.request.path, url_encode(params))


def _update_allowing_pop(params, new_params):
    for k, v in new_params.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v


def _not_defined(x):
    return x is None or x is Undefined


@app.route('/')
def index():
    delta = flask.request.args.get("delta", default=0, type=int)
    day_bin = DayBin()
    secrets = config.get_secrets()
    toggl_api = TogglApi(secrets=secrets)
    jira_api = create_jira_api(secrets)
    today = day_bin.date_of(aware_now())

    if toggl_api.secrets is None:
        return flask.render_template("setup.html")

    min_datetime = day_bin.start_datetime_of(today) + datetime.timedelta(days=delta - 7)
    max_datetime = day_bin.end_datetime_of(today) + datetime.timedelta(days=delta)

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
    pairings = calculate_pairing(toggl_worklog, jira_worklog)
    rows = [
        {
            "toggl": pairing["toggl"],
            "jira": pairing["jira"],
            "dist": pairing["dist"],
            "start": pairing["start"],
            "messages": list(actions.gather_diff(pairing)),
        }
        for pairing in pairings
    ]
    days = utils.into_bins(rows, lambda e: day_bin.date_of(e["start"]), sorting='desc')

    model = dict(
        days=days,
        delta=delta,
    )
    return flask.render_template("index.html", model=model, **model)


def main():
    args = config.parse_args()
    app.run(debug=args.debug)
