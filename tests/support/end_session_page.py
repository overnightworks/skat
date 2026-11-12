from html.parser import HTMLParser


class EndSessionPage(HTMLParser):
    """The form webauth's logout page posts: its action, hidden fields and button text."""

    def __init__(self, markup: str) -> None:
        super().__init__()
        self.action = ""
        self.fields: dict[str, str] = {}
        self.button_label = ""
        self.language = ""
        self._in_button = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.language = attributes["lang"]
        elif tag == "form":
            self.action = attributes["action"]
        elif tag == "input":
            self.fields[attributes["name"]] = attributes["value"]
        elif tag == "button":
            self._in_button = True

    def handle_endtag(self, tag):
        self._in_button = self._in_button and tag != "button"

    def handle_data(self, data):
        if self._in_button:
            self.button_label += data
