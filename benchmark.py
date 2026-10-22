"""
benchmark.py - Feature 10: Performance analysis
-----------------------------------------------------------------------------
  A.  Shortest path on a sparse city grid:
        Dijkstra (array O(V^2)) vs Dijkstra (binary heap, heapq)
        vs Dijkstra (Fibonacci heap) vs A* (Fibonacci heap)
        metrics: avg time per query, nodes settled, route cost agreement
  A2. Same on a DENSE network (E >> V) where decrease-key dominates
  B.  Priority queue: Fibonacci heap vs binary heap (heapq) vs sorted list
      on an insert / decrease-key / extract-min workload
  C.  "Which warehouses stock product X (and Y)?":
        our Inverted HashMap vs Python dict index vs sorted-key binary search
        (BST-style) vs linear scan of all warehouses
Run:  python benchmark.py          (about 20-40 seconds)
      python benchmark.py --quick  (smaller sizes, ~5 seconds)
"""
import bisect
import heapq
import random
import sys
import time

from fibonacci_heap import FibonacciHeap
from inverted_hashmap import InvertedHashMap
from temporal_multigraph import TemporalMultigraph, EXPRESSWAY, ARTERIAL, LOCAL
from algorithms import dijkstra_array, dijkstra_binary, dijkstra_fib, astar_fib

QUICK = "--quick" in sys.argv


def ms(t0):
    return (time.perf_counter() - t0) * 1000


def build_city(side, rng):
    """Jittered grid city: local/arterial roads to right & down neighbours,
    ~15% of links get a parallel expressway, plus some expressway shortcuts."""
    g = TemporalMultigraph()
    for r in range(side):
        for c in range(side):
            g.add_location("n", c + rng.uniform(-0.3, 0.3), r + rng.uniform(-0.3, 0.3))
    for r in range(side):
        for c in range(side):
            a = r * side + c
            for rr, cc in ((r, c + 1), (r + 1, c)):
                if rr >= side or cc >= side:
                    continue
                b = rr * side + cc
                art = r % 5 == 0 or c % 5 == 0
                g.add_road(a, b, "r", ARTERIAL if art else LOCAL, 45 if art else 28)
                if rng.random() < 0.15:
                    g.add_road(a, b, "x", EXPRESSWAY, 80)              # parallel edge
    n = side * side
    for _ in range(n // 50):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b and g.euclid(a, b) < 8:
            g.add_road(a, b, "x", EXPRESSWAY, 80)
    return g


def bench_paths():
    print("\nA. SHORTEST PATH ON A TEMPORAL MULTIGRAPH (departure 08:30, rush hour)")
    print(f"{'V':<8}{'E':<8}{'Algorithm':<24}{'avg ms/query':>13}{'avg settled':>13}{'same cost':>11}")
    rng = random.Random(42)
    sides = (20, 50) if QUICK else (20, 50, 100)
    for side in sides:
        g = build_city(side, rng)
        n = g.node_count()
        Q = 10
        qs = [(rng.randrange(n), rng.randrange(n)) for _ in range(Q)]
        ref = [dijkstra_fib(g, s, t, 510).arrive for s, t in qs]
        algos = [
            ("Dijkstra + array", dijkstra_array, n <= 2500),
            ("Dijkstra + binary heap", dijkstra_binary, True),
            ("Dijkstra + Fib heap", dijkstra_fib, True),
            ("A* + Fib heap", astar_fib, True),
        ]
        for name, f, run in algos:
            if not run:
                print(f"{n:<8}{g.edge_count():<8}{name:<24}{'skipped':>13}{'(O(V^2))':>13}{'-':>11}")
                continue
            settled = same = 0
            t0 = time.perf_counter()
            for i, (s, t) in enumerate(qs):
                p = f(g, s, t, 510)
                settled += p.settled
                same += abs(p.arrive - ref[i]) < 1e-6
            print(f"{n:<8}{g.edge_count():<8}{name:<24}{ms(t0) / Q:>13.2f}{settled // Q:>13}{f'{same}/{Q}':>11}")


def bench_dense():
    print("\nA2. DENSE NETWORK (E >> V): where decrease-key dominates")
    print(f"{'V':<8}{'E':<9}{'Algorithm':<24}{'avg ms/query':>13}{'improvements':>14}{'same':>7}")
    rng = random.Random(11)
    configs = ((300, 0.5),) if QUICK else ((300, 0.5), (700, 0.4))
    for V, density in configs:
        g = TemporalMultigraph()
        for _ in range(V):
            g.add_location("h", rng.uniform(0, 100), rng.uniform(0, 100))
        for a in range(V):
            for b in range(a + 1, V):
                if rng.random() < density:
                    g.add_road(a, b, "l", ARTERIAL, 45, g.euclid(a, b) * (1 + 3 * rng.random()))
        Q = 3
        srcs = [rng.randrange(V) for _ in range(Q)]
        ref = []
        for name, f in (("Dijkstra + binary heap", dijkstra_binary), ("Dijkstra + Fib heap", dijkstra_fib)):
            relax = same = 0
            t0 = time.perf_counter()
            for i, s in enumerate(srcs):
                r = f(g, s, -1, 600)
                relax += r.relaxations
                if not ref or len(ref) < Q:
                    ref.append(r.settled)
                else:
                    same += r.settled == ref[i]
            sm = f"{same}/{Q}" if f is dijkstra_fib else "-"
            print(f"{V:<8}{g.edge_count():<9}{name:<24}{ms(t0) / Q:>13.1f}{relax // Q:>14}{sm:>7}")
    print("  (single source to ALL nodes, as used to build the multi-stop travel-time matrix)")


def bench_heaps():
    print("\nB. PRIORITY QUEUE: N inserts, N decrease-keys, N extract-mins")
    print(f"{'N':<10}{'Structure':<34}{'time ms':>10}")
    rng = random.Random(7)
    for N in ((10000, 50000) if QUICK else (10000, 50000, 200000)):
        init = [rng.uniform(1e6, 2e6) for _ in range(N)]
        who = [rng.randrange(N) for _ in range(N)]

        t0 = time.perf_counter()                   # Fibonacci heap: real decrease-key
        h = FibonacciHeap()
        hd = [h.insert(init[i], i) for i in range(N)]
        cur = init[:]
        for x in who:
            cur[x] -= 1000
            h.decrease_key(hd[x], cur[x])
        while not h.empty():
            h.extract_min()
        print(f"{N:<10}{'Fibonacci heap (pure Python)':<34}{ms(t0):>10.1f}")

        t0 = time.perf_counter()                   # heapq: fake decrease-key with duplicates
        pq = [(init[i], i) for i in range(N)]
        heapq.heapify(pq)
        cur = init[:]
        for x in who:
            cur[x] -= 1000
            heapq.heappush(pq, (cur[x], x))
        while pq:
            heapq.heappop(pq)
        print(f"{N:<10}{'Binary heap heapq (C, lazy dup.)':<34}{ms(t0):>10.1f}")

        if N <= 50000:
            t0 = time.perf_counter()               # sorted list: O(n) insert/delete
            sl = sorted((init[i], i) for i in range(N))
            cur = init[:]
            for x in who:
                del sl[bisect.bisect_left(sl, (cur[x], x))]
                cur[x] -= 1000
                bisect.insort(sl, (cur[x], x))
            while sl:
                sl.pop(0)
            print(f"{N:<10}{'Sorted list + binary search':<34}{ms(t0):>10.1f}")
    print("  Note: heapq is implemented in C, so it wins on raw speed. It has no decrease-key,\n"
          "  delete or merge - it fakes decrease-key by pushing duplicates (memory grows with\n"
          "  every update) and cannot cancel or merge orders at all.")


def bench_index():
    print("\nC. 'WHICH WAREHOUSES STOCK PRODUCT X (and Y)?'  (20,000 queries)")
    print(f"{'W':<7}{'Structure':<34}{'1-product ms':>14}{'2-product ms':>14}")
    rng = random.Random(3)
    P, PER, Q = 5000, 60, 20000
    for W in ((500,) if QUICK else (500, 2000)):
        stock = []
        inv = InvertedHashMap(64)
        dct = {}
        for w in range(W):
            s = set()
            while len(s) < PER:
                s.add(f"sku{rng.randrange(P)}")
            stock.append(s)
            for p in s:
                inv.add(p, w)
                dct.setdefault(p, []).append(w)
        skeys = sorted(dct)                         # BST-style: binary search on sorted keys
        svals = [dct[k] for k in skeys]
        q1 = [f"sku{rng.randrange(P)}" for _ in range(Q)]
        q2 = [f"sku{rng.randrange(P)}" for _ in range(Q)]

        def bst_get(k):
            i = bisect.bisect_left(skeys, k)
            return svals[i] if i < len(skeys) and skeys[i] == k else []

        rows = []
        t0 = time.perf_counter()
        for k in q1:
            inv.count(k)
        a = ms(t0)
        t0 = time.perf_counter()
        for x, y in zip(q1, q2):
            inv.intersect([x, y])
        rows.append(("Inverted HashMap (ours, Python)", a, ms(t0)))

        t0 = time.perf_counter()
        for k in q1:
            len(dct.get(k, ()))
        a = ms(t0)
        t0 = time.perf_counter()
        for x, y in zip(q1, q2):
            set(dct.get(x, ())) & set(dct.get(y, ()))
        rows.append(("Python dict index (built-in, C)", a, ms(t0)))

        t0 = time.perf_counter()
        for k in q1:
            len(bst_get(k))
        a = ms(t0)
        t0 = time.perf_counter()
        for x, y in zip(q1, q2):
            set(bst_get(x)) & set(bst_get(y))
        rows.append(("Sorted keys + binary search (BST)", a, ms(t0)))

        QL = Q // 20                               # linear scan is slow: time 5%, extrapolate
        t0 = time.perf_counter()
        for k in q1[:QL]:
            sum(1 for s in stock if k in s)
        a = ms(t0) * Q / QL
        t0 = time.perf_counter()
        for x, y in zip(q1[:QL], q2[:QL]):
            sum(1 for s in stock if x in s and y in s)
        rows.append(("Linear scan of warehouses*", a, ms(t0) * Q / QL))

        for name, a, b in rows:
            print(f"{W:<7}{name:<34}{a:>14.1f}{b:>14.1f}")
    print("  * extrapolated from 5% of the queries")


if __name__ == "__main__":
    print("PERFORMANCE ANALYSIS - Intelligent Logistics Network (Python)")
    bench_paths()
    bench_dense()
    bench_heaps()
    bench_index()
