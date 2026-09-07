"""Small in-memory authentication helpers; deliberately independent of the desktop."""
from collections import OrderedDict, deque
import hmac
import secrets
import time


def constant_equal(left, right):
    # compare_digest(str, str) rejects non-ASCII; UTF-8 supports real passwords.
    return hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))


class Sessions:
    def __init__(self, ttl=43200, maximum=32, clock=time.monotonic):
        self.ttl, self.maximum, self.clock = ttl, maximum, clock
        self.tokens = OrderedDict()

    def create(self):
        self.prune()
        while len(self.tokens) >= self.maximum:
            self.tokens.popitem(last=False)
        token = secrets.token_urlsafe(40)
        self.tokens[token] = self.clock() + self.ttl
        return token

    def valid(self, token):
        self.prune()
        return bool(token) and token in self.tokens

    def revoke(self, token):
        self.tokens.pop(token, None)

    def prune(self):
        now = self.clock()
        for token, expiry in list(self.tokens.items()):
            if expiry <= now:
                self.tokens.pop(token, None)


class LoginLimiter:
    """Bounded per-peer attempt buckets. Does not trust forwarded IP headers."""
    def __init__(self, maximum=8, window=60, peers=1024, clock=time.monotonic):
        self.maximum, self.window, self.peers, self.clock = maximum, window, peers, clock
        self.buckets = OrderedDict()

    def allow(self, peer):
        now = self.clock()
        bucket = self.buckets.setdefault(peer, deque())
        self.buckets.move_to_end(peer)
        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()
        while len(self.buckets) > self.peers:
            self.buckets.popitem(last=False)
        if len(bucket) >= self.maximum:
            return False
        bucket.append(now)
        return True

    def clear(self, peer):
        self.buckets.pop(peer, None)
