"""Simple menu state helper."""


class Menu:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    @property
    def items(self):
        return self._items

    @property
    def index(self):
        return self._index

    def move(self, delta):
        if not self._items or delta == 0:
            return
        count = len(self._items)
        self._index = (self._index + delta) % count

    def selected(self):
        if not self._items:
            return None
        return self._items[self._index]

    def reset(self):
        self._index = 0

