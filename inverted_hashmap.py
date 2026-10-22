"""
inverted_hashmap.py - Inverted index: key (term) -> linked list of ids
-----------------------------------------------------------------------------
A forward map answers "what does warehouse 7 stock?".
An INVERTED map answers the question the dispatcher actually asks:
      "which warehouses stock 'laptop'?"          -> product_index
      "which vehicles are status:AVAILABLE?"       -> vehicle_index
      "which orders are status:PENDING?"           -> order_index

Implementation (hand-written - Python's dict is NOT used for the table):
  * Separate-chaining hash table, FNV-1a hash, power-of-two bucket count,
    automatic rehash when load factor > 0.75      -> O(1) average lookup
  * Each key owns a LinkedList "posting list" of ids
  * add() returns the list node handle so the owner can later delete that
    exact posting in O(1) (e.g. when stock of a product hits 0)
  * intersect([k1, k2, ...]) returns ids present in ALL posting lists,
    e.g. warehouses that stock every product of a multi-item order.

Compared with a BST/AVL keyed by warehouse (suggested in the case study),
a lookup here is O(1) average instead of O(log n) and returns ONLY the
matching warehouses instead of having to visit all of them.
"""
from linked_list import LinkedList

_FNV_OFFSET = 1469598103934665603
_FNV_PRIME = 1099511628211
_MASK64 = (1 << 64) - 1


def fnv1a(s):
    h = _FNV_OFFSET
    for b in s.encode():
        h ^= b
        h = (h * _FNV_PRIME) & _MASK64
    return h


class _Entry:
    __slots__ = ("key", "hash", "postings", "next")

    def __init__(self, key, h):
        self.key = key
        self.hash = h
        self.postings = LinkedList()
        self.next = None          # next entry in the same bucket (chaining)


class InvertedHashMap:
    def __init__(self, initial_buckets=16):
        b = 1
        while b < initial_buckets:
            b <<= 1
        self._buckets = [None] * b
        self._keys = 0

    # ------------------------------------------------------------ public API
    def add(self, key, id_):
        """Add id to key's posting list. O(1) average. Returns a handle."""
        return self._find_or_create(key).postings.push_back(id_)

    def remove(self, key, handle):
        """O(1) removal with the handle returned by add()."""
        e = self._find(key)
        if e is not None and handle is not None:
            e.postings.remove(handle)

    def remove_id(self, key, id_):
        """O(k) removal by value, when no handle is available."""
        e = self._find(key)
        return e.postings.remove_if(lambda x: x == id_) if e else False

    def get(self, key):
        """O(1) average. Returns the posting LinkedList or None."""
        e = self._find(key)
        return e.postings if e else None

    def count(self, key):
        p = self.get(key)
        return len(p) if p else 0

    def to_list(self, key):
        p = self.get(key)
        return list(p) if p else []

    def intersect(self, keys):
        """ids present in every key's posting list. O(sum of posting lengths)."""
        lists = []
        for k in keys:
            p = self.get(k)
            if not p:
                return []          # one empty list -> empty result
            lists.append(p)
        if not lists:
            return []
        # cnt[id] == i means id was seen in lists 0..i-1 -> duplicates never double-count
        cnt = {}
        for i, p in enumerate(lists):
            for id_ in p:
                if cnt.get(id_, 0) == i:
                    cnt[id_] = i + 1
        k = len(lists)
        out, seen = [], set()
        for id_ in lists[-1]:
            if cnt.get(id_) == k and id_ not in seen:
                out.append(id_)
                seen.add(id_)
        return out

    def key_count(self):
        return self._keys

    def bucket_count(self):
        return len(self._buckets)

    def load_factor(self):
        return self._keys / len(self._buckets)

    # -------------------------------------------------------------- internals
    def _find(self, key):
        h = fnv1a(key)
        e = self._buckets[h & (len(self._buckets) - 1)]
        while e is not None:
            if e.hash == h and e.key == key:
                return e
            e = e.next
        return None

    def _find_or_create(self, key):
        e = self._find(key)
        if e is not None:
            return e
        if (self._keys + 1) / len(self._buckets) > 0.75:
            self._rehash(len(self._buckets) * 2)
        h = fnv1a(key)
        e = _Entry(key, h)
        b = h & (len(self._buckets) - 1)
        e.next = self._buckets[b]
        self._buckets[b] = e
        self._keys += 1
        return e

    def _rehash(self, new_size):
        """Entries are re-linked, never copied, so stored handles stay valid."""
        nb = [None] * new_size
        for e in self._buckets:
            while e is not None:
                nxt = e.next
                b = e.hash & (new_size - 1)
                e.next = nb[b]
                nb[b] = e
                e = nxt
        self._buckets = nb
