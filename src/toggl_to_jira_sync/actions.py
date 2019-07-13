class NotificationLevel:
    info = "info"
    warning = "warning"
    danger = "danger"


class SyncValidator(object):
    def __init__(self, message, level, field_name, expected_value):
        self.message = message
        self.level = level
        self.field_name = field_name
        self.expected_value = expected_value

    def check_and_list_messages(self, context):
        original_value = context[self.field_name]
        expected_value = self.expected_value(context)
        if original_value != expected_value:
            yield self.message.format(**context)
            context[self.field_name] = expected_value

