from collections import OrderedDict, namedtuple


class NotificationLevel:
    info = "info"
    warning = "warning"
    danger = "danger"


Action = namedtuple("Action", ["message", "level", "action", "params"])


def gather_diff(pairing):
    context = _extract_context(pairing)
    for validator in validators():
        yield from validator.check_and_list_messages(context)


def _extract_context(pairing):
    toggl = pairing["toggl"]
    jira = pairing["jira"]
    return _merge(
        _map_sys("toggl__", toggl),
        _map_sys("jira__", jira),
        {
            "toggl__id": toggl.tag.id if toggl is not None else None
        }
    )


def _map_sys(prefix, x):
    return {
        prefix + "present": x is not None,
        prefix + "issue": x.issue if x is not None else None,
        prefix + "start": x.start if x is not None else None,
        prefix + "stop": x.stop if x is not None else None,
        prefix + "comment": x.comment if x is not None else None,
    }


def _merge(*dicts):
    result = OrderedDict()
    for x in dicts:
        result.update(x)
    return result


def validators():
    return [
        SyncValidator(
            action="toggl_align_start",
            action_params={"id": "toggl__id"},
            message="Align toggl log start to whole minute {expected_value}.",
            level=NotificationLevel.info,
            field_name="toggl__start",
            expected_value=_whole_minute_of("toggl__start"),
            predicate=_value_of("toggl__present"),
        ),

        # SyncValidator(
        #     message="Align toggl log stop to whole minute {expected_value}.",
        #     field_name="toggl__stop",
        #     expected_value=_whole_minute_of("toggl__stop"),
        #     level=NotificationLevel.info,
        #     predicate=_value_of("toggl__present"),
        # ),
        # PredicateValidator(
        #     message="Create jira worklog for {toggl__issue} {toggl__start} {toggl__stop}",
        #     level=NotificationLevel.danger,
        #     predicate=_value_of("jira__present"),
        # ),
        # SyncValidator(
        #     message="Jira log start {jira__start} does not match Toggl log start {toggl__start}",
        #     field_name="jira__start",
        #     expected_value=_value_of("toggl__start"),
        #     level=NotificationLevel.danger,
        #     predicate=_both_present,
        # ),
        # SyncValidator(
        #     message="Jira log stop {jira__stop} does not match Toggl log stop {toggl__stop}",
        #     field_name="jira__stop",
        #     expected_value=_value_of("toggl__stop"),
        #     level=NotificationLevel.danger,
        #     predicate=_both_present,
        # ),
    ]


class BaseValidator(object):
    def __init__(self, message, level, action, action_params):
        self.message = message
        self.level = level
        self.action = action
        self.action_params = action_params

    def check_and_list_messages(self, context):
        raise NotImplemented

    def make_action(self, context, expected_value=None):
        temp_context = dict()
        temp_context.update(context)
        temp_context["expected_value"] = expected_value
        message = self.message.format(**temp_context)
        action_params = None
        if self.action_params:
            action_params = {
                k: temp_context[v]
                for k, v in self.action_params.items()
            }
        return Action(
            action=self.action,
            params=action_params,
            message=message,
            level=self.level,
        )


class SyncValidator(BaseValidator):
    def __init__(self, message, level, action, action_params, field_name=None, expected_value=None, predicate=None):
        if predicate is None:
            predicate = _always
        super().__init__(message=message, level=level, action=action, action_params=action_params)
        self.field_name = field_name
        self.expected_value = expected_value
        self.predicate = predicate

    def check_and_list_messages(self, context):
        if not self.predicate(context):
            return
        original_value = context[self.field_name]
        expected_value = self.expected_value(context)
        if original_value == expected_value:
            return
        yield self.make_action(context, expected_value)
        context[self.field_name] = expected_value


class PredicateValidator(BaseValidator):
    def __init__(self, message, level, action, action_params, predicate):
        super().__init__(message=message, level=level, action=action, action_params=action_params)
        self.predicate = predicate

    def check_and_list_messages(self, context):
        if self.predicate(context):
            return
        yield self.make_action(context)


def _always(context):
    return True


def _both_present(context):
    return context["toggl__start"] and context["jira__start"]


def _to_whole_minute(dt):
    if dt is None:
        return None
    return dt.replace(second=0, microsecond=0)


def _whole_minute_of(key):
    return lambda context: _to_whole_minute(context[key])


def _value_of(key):
    return lambda context: context[key]
