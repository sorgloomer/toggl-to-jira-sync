import datetime
from collections import namedtuple, OrderedDict

from tzlocal import get_localzone

WorklogEntry = namedtuple("WorklogEntry", [
    "issue",
    "start",
    "stop",
    "comment",
    "tag",
])


def calculate_pairing(toggl_logs, jira_logs):
    pairings = _calculate_pairing(toggl_logs, jira_logs, _worklog_entry_distance, 5)
    return sorted(
        [
            {
                "toggl": pairing[0],
                "jira": pairing[1],
                "dist": pairing[2],
                "start": _pairing_start(pairing),
            }
            for pairing in pairings
        ],
        key=lambda pairing: pairing["start"],
        reverse=True,
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


def _pairing_start(pairing):
    toggl_entry, jira_entry, dist = pairing
    if toggl_entry is not None:
        return toggl_entry.start
    if jira_entry is not None:
        return jira_entry.start
    return None


def _worklog_entry_distance(a, b):
    return (
        + 100 * _worklog_str_dist(a.issue, b.issue)
        + 1 * _worklog_str_dist(a.comment, b.comment)
        + 2 * _worklog_datetime_dist(a.start, b.start)
        + 1 * _worklog_datetime_dist(a.stop, b.stop)
    )


def _worklog_str_dist(x, y):
    return 0 if x == y else 1


def _worklog_datetime_dist(dt1, dt2):
    return abs(dt1 - dt2) / datetime.timedelta(minutes=60)


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
