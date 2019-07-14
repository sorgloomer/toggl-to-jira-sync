import datetime


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
datetime_jira_format = DatetimeFormat("%Y-%m-%dT%H:%M:%S.000%z")
datetime_toggl_format = DatetimeTogglFormat()
