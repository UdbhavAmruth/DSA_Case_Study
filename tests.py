"""
tests.py - Correctness tests for the four data structures
Run:  python tests.py
"""
import random
import unittest

from linked_list import LinkedList
from fibonacci_heap import FibonacciHeap
from inverted_hashmap import InvertedHashMap
from temporal_multigraph import TemporalMultigraph, EXPRESSWAY, LOCAL
from algorithms import (dijkstra_fib, dijkstra_binary, dijkstra_array, astar_fib,
                        bridges_and_cuts)


class TestLinkedList(unittest.TestCase):
    def test_handles_and_splice(self):
        a, b = LinkedList(), LinkedList()
        n1 = a.push_back(1)
        a.push_back(2)
        n3 = a.push_back(3)
        a.push_front(0)
        a.remove(n1)
        a.remove(n3)
        self.assertEqual(a.to_list(), [0, 2])
        b.push_back(7)
        b.push_back(8)
        a.splice(b)
        self.assertEqual(len(a), 4)
        self.assertEqual(len(b), 0)
        self.assertEqual(a.tail.data, 8)
        self.assertEqual(a.pop_front(), 0)
        self.assertEqual(a.to_list(), [2, 7, 8])


class TestFibonacciHeap(unittest.TestCase):
    def test_random_operations_against_reference(self):
        """60k random insert / decrease-key / extract-min / remove vs a brute-force reference."""
        rng = random.Random(1)
        h = FibonacciHeap()
        live, ref, ids = {}, {}, []      # id -> handle, id -> key, list of live ids
        pos = {}                         # id -> index in ids (for O(1) random removal)

        def forget(i):
            j = pos.pop(i)
            last = ids.pop()
            if last != i:
                ids[j] = last
                pos[last] = j
            del ref[i], live[i]

        next_id = 0
        for _ in range(60000):
            op = rng.randrange(10)
            if op < 4 or not ids:
                k = rng.randrange(100000)
                live[next_id] = h.insert(k, next_id)
                ref[next_id] = k
                pos[next_id] = len(ids)
                ids.append(next_id)
                next_id += 1
            elif op < 7:
                i = rng.choice(ids)
                nk = ref[i] - rng.randrange(5000)
                h.decrease_key(live[i], nk)
                ref[i] = nk
            elif op < 9:
                k, v = h.extract_min()
                self.assertEqual(k, min(ref.values()))
                self.assertEqual(k, ref[v])
                forget(v)
            else:
                i = rng.choice(ids)
                h.remove(live[i])
                forget(i)
            self.assertEqual(len(h), len(ref))
        drained = [h.extract_min()[0] for _ in range(len(h))]
        self.assertEqual(drained, sorted(ref.values()))

    def test_merge(self):
        a, b = FibonacciHeap(), FibonacciHeap()
        for i in range(100):
            a.insert(2 * i, None)
            b.insert(2 * i + 1, None)
        a.merge(b)
        self.assertEqual(len(a), 200)
        self.assertTrue(b.empty())
        self.assertEqual([a.extract_min()[0] for _ in range(200)], list(range(200)))

    def test_tuple_keys(self):
        h = FibonacciHeap()
        n = h.insert((5, 600.0, 0), "low")
        h.insert((2, 700.0, 1), "mid")
        h.decrease_key(n, (1, 600.0, 0))          # escalation
        self.assertEqual(h.extract_min()[1], "low")


class TestInvertedHashMap(unittest.TestCase):
    def test_add_remove_rehash(self):
        m = InvertedHashMap(4)
        handles = [m.add(f"k{i % 100}", i) for i in range(1000)]
        self.assertEqual(m.key_count(), 100)
        self.assertEqual(m.count("k7"), 10)
        self.assertLessEqual(m.load_factor(), 0.75)
        m.remove("k7", handles[7])                # handle still valid after rehashes
        self.assertEqual(m.count("k7"), 9)
        self.assertIsNone(m.get("missing"))

    def test_intersect(self):
        w = InvertedHashMap()
        for i in (1, 2, 3):
            w.add("laptop", i)
        for i in (2, 3, 4):
            w.add("phone", i)
        w.add("tv", 3)
        self.assertEqual(set(w.intersect(["laptop", "phone"])), {2, 3})
        self.assertEqual(w.intersect(["laptop", "phone", "tv"]), [3])
        self.assertEqual(w.intersect(["laptop", "fridge"]), [])


class TestTemporalMultigraph(unittest.TestCase):
    def test_all_shortest_path_algorithms_agree(self):
        rng = random.Random(9)
        g = TemporalMultigraph()
        for _ in range(300):
            g.add_location("n", rng.uniform(0, 30), rng.uniform(0, 30))
        for _ in range(1200):
            a, b = rng.randrange(300), rng.randrange(300)
            if a != b:
                g.add_road(a, b, "r", rng.randrange(3), 30 + rng.randrange(50))
        for _ in range(30):
            s, t, t0 = rng.randrange(300), rng.randrange(300), rng.randrange(1440)
            ref = dijkstra_fib(g, s, t, t0).arrive
            for f in (dijkstra_binary, dijkstra_array, astar_fib):
                self.assertAlmostEqual(f(g, s, t, t0).arrive, ref, places=9)

    def test_parallel_edges_and_closures(self):
        h = TemporalMultigraph()
        A, B = h.add_location("A", 0, 0), h.add_location("B", 10, 0)
        slow = h.add_road(A, B, "slow", LOCAL, 20, 10)
        fast = h.add_road(A, B, "fast", EXPRESSWAY, 80, 10)
        self.assertEqual(h.multiplicity(A, B), 2)
        self.assertEqual(dijkstra_fib(h, A, B, 840).edges[0], fast)
        h.add_closure(fast, 600, 720)
        self.assertEqual(dijkstra_fib(h, A, B, 650).edges[0], slow)   # closed now
        self.assertEqual(dijkstra_fib(h, A, B, 730).edges[0], fast)   # reopened later
        self.assertEqual(bridges_and_cuts(h, 840)[0], [])             # 2 parallel -> no bridge
        self.assertEqual(len(bridges_and_cuts(h, 650)[0]), 1)         # only 1 open -> bridge


if __name__ == "__main__":
    unittest.main(verbosity=2)
