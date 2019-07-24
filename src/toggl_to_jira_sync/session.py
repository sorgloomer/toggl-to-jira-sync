from flask.sessions import SessionInterface, SessionMixin


class Session(dict, SessionMixin):
    pass


class SingletonMemorySessionInterface(SessionInterface):
    def __init__(self):
        super().__init__()
        self.session = Session()

    def open_session(self, app, request):
        return self.session

    def save_session(self, app, session, response):
        pass
