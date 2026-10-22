"""
fibonacci_heap.py - Min Fibonacci heap with handles
-----------------------------------------------------------------------------
Amortised costs:
    insert         O(1)        merge (meld)      O(1)
    find_min       O(1)        decrease_key      O(1)
    extract_min    O(log n)    remove(handle)    O(log n)

Used for TWO jobs in this project:
 1) Dijkstra / A* priority queue. Dijkstra does up to E decrease-key
    operations; with a binary heap each costs O(log V) => O((V+E) log V).
    With a Fibonacci heap decrease-key is O(1) => O(E + V log V).
 2) The global delivery-order queue:
      - an order escalates (deadline approaching)  -> decrease_key  O(1)
      - a cancelled order is pulled out            -> remove        O(log n)
      - a broken vehicle's orders are put back     -> merge         O(1)
    Python's heapq (a binary heap) supports none of these three operations.

Structure: every node sits in a circular doubly linked list of siblings
(the root list or a child list). A node has parent, one child pointer,
degree and a 'mark' bit used by cascading cuts.
Keys may be any comparable values (numbers, tuples, ...).
"""
import math


class FibNode:
    __slots__ = ("key", "value", "parent", "child", "left", "right", "degree", "mark")

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.parent = None
        self.child = None
        self.left = self
        self.right = self
        self.degree = 0
        self.mark = False


def _siblings(start):
    """List all nodes of a circular sibling list (snapshot, safe to modify)."""
    out = []
    if start is None:
        return out
    n = start
    while True:
        out.append(n)
        n = n.right
        if n is start:
            return out


class FibonacciHeap:
    def __init__(self):
        self.min = None
        self._n = 0

    def __len__(self):
        return self._n

    def empty(self):
        return self._n == 0

    def top(self):
        return self.min

    # O(1)
    def insert(self, key, value):
        x = FibNode(key, value)
        self._add_root(x)
        if self.min is None or x.key < self.min.key:
            self.min = x
        self._n += 1
        return x

    # O(1) - steals every node of `other`; other becomes empty
    def merge(self, other):
        if other.min is None:
            return
        if self.min is None:
            self.min = other.min
        else:
            a = self.min.right
            b = other.min.left
            self.min.right = other.min
            other.min.left = self.min
            a.left = b
            b.right = a
            if other.min.key < self.min.key:
                self.min = other.min
        self._n += other._n
        other.min = None
        other._n = 0

    # O(log n) amortised. Returns (key, value).
    def extract_min(self):
        z = self.min
        if z is None:
            raise IndexError("extract_min on empty heap")
        for c in _siblings(z.child):              # children become roots
            c.parent = None
            c.mark = False
            self._add_root(c)
        z.child = None
        self._unlink(z)
        if z.right is z:
            self.min = None
        else:
            self.min = z.right
            self._consolidate()
        self._n -= 1
        z.left = z.right = z
        return z.key, z.value

    # O(1) amortised. new_key must not be greater than the current key.
    def decrease_key(self, x, new_key):
        if x.key < new_key:
            raise ValueError("decrease_key: new key is larger than current key")
        x.key = new_key
        y = x.parent
        if y is not None and x.key < y.key:
            self._cut(x, y)
            self._cascading_cut(y)
        if x.key < self.min.key:
            self.min = x

    # O(log n) amortised - delete an arbitrary node through its handle
    def remove(self, x):
        y = x.parent
        if y is not None:
            self._cut(x, y)
            self._cascading_cut(y)
        self.min = x              # force x to be the minimum, then pop it
        self.extract_min()

    # ---------------------------------------------------------------- helpers
    def _add_root(self, x):
        x.parent = None
        if self.min is None:
            x.left = x.right = x
            self.min = x
            return
        x.left = self.min
        x.right = self.min.right
        self.min.right.left = x
        self.min.right = x

    @staticmethod
    def _unlink(x):
        x.left.right = x.right
        x.right.left = x.left

    def _link(self, y, x):          # make y a child of x
        self._unlink(y)
        y.left = y.right = y
        y.parent = x
        if x.child is None:
            x.child = y
        else:
            y.left = x.child
            y.right = x.child.right
            x.child.right.left = y
            x.child.right = y
        x.degree += 1
        y.mark = False

    def _consolidate(self):
        size = int(math.log(self._n + 1, 1.618)) + 3
        A = [None] * size
        for w in _siblings(self.min):
            x = w
            d = x.degree
            while True:
                if d >= len(A):
                    A.extend([None] * len(A))
                y = A[d]
                if y is None:
                    break
                if y.key < x.key:
                    x, y = y, x
                self._link(y, x)
                A[d] = None
                d += 1
            A[d] = x
        self.min = None
        for x in A:
            if x is None:
                continue
            if self.min is None:
                x.left = x.right = x
                self.min = x
            else:
                x.left = self.min
                x.right = self.min.right
                self.min.right.left = x
                self.min.right = x
                if x.key < self.min.key:
                    self.min = x

    def _cut(self, x, y):           # remove x from the child list of y
        if x.right is x:
            y.child = None
        else:
            if y.child is x:
                y.child = x.right
            self._unlink(x)
        y.degree -= 1
        x.left = x.right = x
        self._add_root(x)
        x.mark = False

    def _cascading_cut(self, y):
        while True:
            z = y.parent
            if z is None:
                return
            if not y.mark:
                y.mark = True
                return
            self._cut(y, z)
            y = z
