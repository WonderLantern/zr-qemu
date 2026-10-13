# SPDX-License-Identifier: GPL-2.0-or-later


class Group:
    """Let unrelated one-shot observers handle all stopped CPUs before cont."""
    def __init__(self, *observers):
        self.observers = [o for o in observers if o is not None]

    def handle(self):
        found = False
        for observer in self.observers:
            found = observer.handle() or found
        return found

    def close(self):
        for observer in self.observers:
            observer.close()
