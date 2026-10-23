"""
linked_list.py - Doubly linked list with O(1) node handles
-----------------------------------------------------------------------------
Used everywhere in the project:
  * posting lists inside the Inverted HashMap
  * adjacency lists (edge ids) of the Temporal Multigraph
  * road-closure time windows on each edge
  * each vehicle's list of pending orders

Why a hand-made doubly linked list instead of a Python list?
  push_back() returns the Node object itself (a "handle"). Whoever keeps the
  handle can later remove that element in O(1) without searching - e.g. a
  delivered order is unlinked from its vehicle instantly, a warehouse that
  runs out of a product is unlinked from that product's posting list instantly.
  A Python list needs list.remove(x): an O(n) search plus an O(n) shift.
  splice() moves a whole list onto another in O(1) (used on breakdowns).
"""


class Node:
    __slots__ = ("data", "prev", "next")

    def __init__(self, data):
        self.data = data
        self.prev = None
        self.next = None


class LinkedList:
    __slots__ = ("head", "tail", "_size")

    def __init__(self):
        self.head = None
        self.tail = None
        self._size = 0

    # O(1)
    def push_back(self, value):
        n = Node(value)
        n.prev = self.tail
        if self.tail:
            self.tail.next = n
        else:
            self.head = n
        self.tail = n
        self._size += 1
        return n

    # O(1)
    def push_front(self, value):
        n = Node(value)
        n.next = self.head
        if self.head:
            self.head.prev = n
        else:
            self.tail = n
        self.head = n
        self._size += 1
        return n

    # O(1) - remove using a handle returned by push_back / push_front
    def remove(self, n):
        if n is None:
            return
        if n.prev:
            n.prev.next = n.next
        else:
            self.head = n.next
        if n.next:
            n.next.prev = n.prev
        else:
            self.tail = n.prev
        n.prev = n.next = None
        self._size -= 1

    # O(1)
    def pop_front(self):
        if self.head is None:
            raise IndexError("pop_front on empty list")
        v = self.head.data
        self.remove(self.head)
        return v

    # O(1) - move every node of `other` to the end of this list
    def splice(self, other):
        if other.head is None:
            return
        if self.head is None:
            self.head, self.tail = other.head, other.tail
        else:
            self.tail.next = other.head
            other.head.prev = self.tail
            self.tail = other.tail
        self._size += other._size
        other.head = other.tail = None
        other._size = 0

    # O(n) - fallback removal by value when no handle was kept
    def remove_if(self, pred):
        n = self.head
        while n:
            if pred(n.data):
                self.remove(n)
                return True
            n = n.next
        return False

    def clear(self):
        self.head = self.tail = None
        self._size = 0

    def __len__(self):
        return self._size

    def __bool__(self):
        return self._size > 0

    def __iter__(self):
        n = self.head
        while n:
            nxt = n.next          # safe even if the caller removes n
            yield n.data
            n = nxt

    def to_list(self):
        return list(self)
