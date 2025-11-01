"""Hierarchical menu state helper with scrolling support."""


class Menu:
    def __init__(self, title, items, parent=None, visible_count=3):
        self.title = title
        self.parent = parent
        self._items = list(items)
        self._index = 0
        self._view_offset = 0
        self._visible_count = max(1, visible_count)

    @property
    def items(self):
        return self._items

    @property
    def index(self):
        return self._index

    @property
    def view_offset(self):
        return self._view_offset

    @property
    def visible_count(self):
        return self._visible_count

    def set_items(self, items):
        self._items = list(items)
        self.reset()

    def set_parent(self, parent):
        self.parent = parent

    def set_visible_count(self, count):
        self._visible_count = max(1, count)
        self.ensure_visible()

    def move(self, delta):
        if not self._items or delta == 0:
            return
        count = len(self._items)
        self._index = (self._index + delta) % count
        self.ensure_visible()

    def ensure_visible(self):
        count = len(self._items)
        if count == 0:
            self._index = 0
            self._view_offset = 0
            return
        if self._index < 0:
            self._index = 0
        elif self._index >= count:
            self._index = count - 1
        if self._index < self._view_offset:
            self._view_offset = self._index
        elif self._index >= self._view_offset + self._visible_count:
            self._view_offset = self._index - self._visible_count + 1
        max_offset = max(0, count - self._visible_count)
        if self._view_offset > max_offset:
            self._view_offset = max_offset
        if self._view_offset < 0:
            self._view_offset = 0

    def get_visible_items(self):
        if not self._items:
            return []
        end = min(self._view_offset + self._visible_count, len(self._items))
        return self._items[self._view_offset:end]

    def selected(self):
        if not self._items:
            return None
        return self._items[self._index]

    def reset(self):
        self._index = 0
        self._view_offset = 0

