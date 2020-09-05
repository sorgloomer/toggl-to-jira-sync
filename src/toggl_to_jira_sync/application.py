import datetime
import json
import pprint
import time
from collections import namedtuple

import flask
from jinja2 import Undefined
from markupsafe import Markup
from tzlocal import get_localzone
from werkzeug.urls import url_encode

from . import settingsloader, utils, actions, service, api_controller
from .api_service import determine_actions_and_map
from .core import DayBin, calculate_pairing
from .formats import datetime_toggl_format, datetime_my_date_format
from .service import aware_now
from .session import SingletonMemorySessionInterface

app = flask.Flask(__name__)
app.config.from_pyfile('config/default.py')
app.config.from_envvar('APP_CONFIG_FILE', silent=True)
app.session_interface = SingletonMemorySessionInterface()

app.last_request_time = 0.0


@app.before_request
def request_timestamp():
    if flask.request.path != "/attempt-shutdown":
        app.last_request_time = time.monotonic()
    app.logger.info("Serving request %s", flask.request.path)


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


IndexArgs = namedtuple("IndexArgs", ["delta"])


@app.route('/')
def index():
    args = _get_index_args()
    model = _ensure_model(args.delta)
    return flask.render_template("index.html", model=model, **model)


@app.route('/', methods=["POST"])
def index_post():
    args = _get_index_args()
    action = flask.request.form.get("action")
    if action == "refresh":
        _ensure_model(args.delta, force_refresh=True)
        return reload_using_get()
    if action == "sync":
        action_day = flask.request.form.get("day")
        days = _ensure_model(args.delta)["days"]
        day = utils.first(days, lambda d: d["key"] == action_day)
        flask.session["running_action"] = SyncState(day["actions"])
        return flask.redirect(flask.url_for("execute_actions"))
    raise KeyError("Unknown action {action}".format(action=action))


class SyncState(object):
    def __init__(self, actions, index=0):
        self.actions = actions
        self.index = index


def reload_using_get():
    return flask.redirect(flask.request.url)


def _get_index_args():
    delta = flask.request.args.get("delta", default=0, type=int)
    return IndexArgs(delta=delta)


def _ensure_model(delta, force_refresh=False):
    session = flask.session
    model = session.get("model")
    if force_refresh or model is None or model["delta"] != delta:
        model = _fetch_model(delta)
        session["model"] = model
    return model


def _fetch_model(delta):
    day_bin = DayBin()
    settings = settingsloader.get_settings()
    apis = service.get_apis(settings=settings)
    today = day_bin.date_of(aware_now())

    if apis.secrets is None:
        return flask.render_template("setup.html")

    min_datetime = day_bin.start_datetime_of(today) + datetime.timedelta(days=delta - 7)
    max_datetime = day_bin.end_datetime_of(today) + datetime.timedelta(days=delta)

    jira_worklog = apis.jira.get_worklog(
        author=apis.secrets.jira_username,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    toggl_worklog = apis.toggl.get_worklog(
        workspace_name=settings.toggl_workspace_name,
        min_datetime=min_datetime,
        max_datetime=max_datetime,
    )
    pairings = calculate_pairing(toggl_worklog["worklog"], jira_worklog["worklog"])
    diff_gatherer = actions.DiffGather(settings=settings, projects=toggl_worklog["projects"])
    rows = [
        determine_actions_and_map(pairing, diff_gatherer)
        for pairing in pairings
    ]
    days = utils.into_bins(rows, lambda e: day_bin.date_of(e["start"]), sorting='desc')
    days = [aggregate_actions(day) for day in days]

    return dict(
        days=days,
        delta=delta,
        projects=toggl_worklog["projects"],
        entries=toggl_worklog["entries"],
    )


def invalidate_cached_model():
    flask.session["model"] = None


@app.route('/execute-actions', methods=["GET", "POST"])
def execute_actions():
    action_state = flask.session["running_action"]
    action_list = action_state.actions
    action_index = action_state.index

    finished = True
    if action_index < len(action_list):
        finished = False
        if flask.request.method == "POST":
            action = action_list[action_index]
            service.ActionExecutor().execute(action)
            action_state.index += 1
    else:
        invalidate_cached_model()
    display_action_index = min(action_index + 1, len(action_list))
    return flask.render_template(
        "execute-actions.html",
        finished=finished,
        action_list=action_list,
        action_index=action_index,
        display_action_index=display_action_index,
    )


@app.route('/attempt-shutdown', methods=["POST"])
def handle_attempt_shutdown():
    attempt_shutdown_time = time.monotonic()
    time.sleep(0.5)  # to see if anyone is still making requests, like a page reload
    if app.last_request_time < attempt_shutdown_time - 0.5:
        shutdown_server()
        return "Server shutting down...\n<script>window.close();</script>"
    else:
        return "Some new requests prevented shutdown."


def shutdown_server():
    func = flask.request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


def aggregate_actions(day):
    actions = [
        action
        for pairing in day[1]
        for action in pairing["actions"]
    ]
    return {
        "key": datetime_my_date_format.to_str(day[0]),
        "day": day[0],
        "pairings": day[1],
        "actions": actions,
        "sync_form": {
            "actions": json.dumps(actions)
        }
    }


def main():
    args = settingsloader.parse_args()
    app.run(debug=args.debug)


api_controller.api_routes(app)
