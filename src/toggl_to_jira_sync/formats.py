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


class DatetimeJiraFormat(DatetimeFormat):
    def __init__(self):
        super().__init__("%Y-%m-%dT%H:%M:%S.%f%z")

    def to_str(self, dt):
        if dt is None:
            return None
        return self._shrink(super().to_str(dt))

    def from_str(self, s):
        if s is None:
            return None
        return super().from_str(self._expand(s))

    def _shrink(self, param):
        if len(param) != 31:
            return param
        return param[:23] + param[26:]

    def _expand(self, s):
        if len(s) != 28:
            return s
        return s[:23] + "000" + s[23:]


datetime_my_date_format = DatetimeFormat("%Y-%m-%d")
datetime_jira_date_format = DatetimeFormat("%Y-%m-%d")
datetime_jira_format = DatetimeJiraFormat()
datetime_toggl_format = DatetimeTogglFormat()
