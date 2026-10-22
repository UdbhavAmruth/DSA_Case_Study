"""
algorithms.py - Graph algorithms on the Temporal Multigraph
-----------------------------------------------------------------------------
  * dijkstra_fib     : time-dependent Dijkstra, Fibonacci heap   O(E + V log V)
  * dijkstra_binary  : same, heapq binary heap (lazy deletion)   O((V+E) log V)
  * dijkstra_array   : same, plain array scan                    O(V^2)
  * astar_fib        : time-dependent A*, Fibonacci heap, straight-line heuristic
  * bfs_reachable    : BFS over roads open at time t
  * components       : DFS connected components at time t
  * bridges_and_cuts : Tarjan - bottleneck roads (bridges) and critical
                       junctions (articulation points). Works on a MULTIgraph
                       because the DFS skips the parent EDGE id, not the parent
                       node, so a pair joined by two parallel roads is
                       correctly NOT a bridge.
  * alternate_routes : best route + detours obtained by blocking each edge
  * multi_stop       : nearest-neighbour + 2-opt with deadline penalty

Time-dependent Dijkstra labels each node with its EARLIEST ARRIVAL TIME.
Relaxing edge (u, v) costs travel_time(e, arrival[u]), i.e. the cost is read
at the moment the vehicle actually reaches the road. This is correct under the
FIFO property (leaving later never makes you arrive earlier), which our
continuous, interpolated traffic profile is designed to keep.
"""
import heapq
import sys
from fibonacci_heap import FibonacciHeap
from temporal_multigraph import INF


class PathResult:
    __slots__ = ("found", "depart", "arrive", "nodes", "edges", "times", "settled", "relaxations")

    def __init__(self, depart):
        self.found = False
        self.depart = depart
        self.arrive = INF
        self.nodes = []        # node sequence
        self.edges = []        # edge ids used (identifies WHICH parallel road)
        self.times = []        # arrival time at each node
        self.settled = 0       # nodes popped from the queue
        self.relaxations = 0   # successful label improvements

    @property
    def minutes(self):
        return self.arrive - self.depart


def _build_path(g, src, dst, t0, arr, via, settled, relax):
    r = PathResult(t0)
    r.settled, r.relaxations = settled, relax
    if dst is None or dst < 0 or arr[dst] == INF:
        return r
    r.found = True
    r.arrive = arr[dst]
    v = dst
    while v != src:
        r.nodes.append(v)
        r.times.append(arr[v])
        e = via[v]
        r.edges.append(e)
        v = g.edges[e].other(v)
    r.nodes.append(src)
    r.times.append(arr[src])
    r.nodes.reverse()
    r.times.reverse()
    r.edges.reverse()
    return r


def dijkstra_fib(g, src, dst, t0, all_arrival=None, blocked=None):
    """Dijkstra with a Fibonacci heap. dst=-1 -> compute arrival at every node
    (pass a list as all_arrival to receive it). blocked = set of edge ids to avoid."""
    n = g.node_count()
    arr = [INF] * n
    via = [-1] * n
    handle = [None] * n
    done = [False] * n
    pq = FibonacciHeap()
    arr[src] = t0
    handle[src] = pq.insert(t0, src)
    settled = relax = 0
    edges, nodes = g.edges, g.nodes
    while not pq.empty():
        t, u = pq.extract_min()
        handle[u] = None
        done[u] = True
        settled += 1
        if u == dst:
            break
        for eid in nodes[u].adj:
            if blocked and eid in blocked:
                continue
            v = edges[eid].other(u)
            if done[v]:
                continue
            tt = g.travel_time(eid, t)
            if tt == INF:
                continue
            na = t + tt
            if na < arr[v]:
                arr[v] = na
                via[v] = eid
                relax += 1
                if handle[v] is not None:
                    pq.decrease_key(handle[v], na)        # O(1) amortised
                else:
                    handle[v] = pq.insert(na, v)
    if all_arrival is not None:
        all_arrival[:] = arr
    return _build_path(g, src, dst, t0, arr, via, settled, relax)


def dijkstra_binary(g, src, dst, t0):
    """Baseline: binary heap (heapq) with lazy deletion of stale entries."""
    n = g.node_count()
    arr = [INF] * n
    via = [-1] * n
    done = [False] * n
    arr[src] = t0
    pq = [(t0, src)]
    settled = relax = 0
    edges, nodes = g.edges, g.nodes
    while pq:
        t, u = heapq.heappop(pq)
        if done[u]:
            continue                      # stale duplicate
        done[u] = True
        settled += 1
        if u == dst:
            break
        for eid in nodes[u].adj:
            v = edges[eid].other(u)
            if done[v]:
                continue
            tt = g.travel_time(eid, t)
            if tt != INF and t + tt < arr[v]:
                arr[v] = t + tt
                via[v] = eid
                relax += 1
                heapq.heappush(pq, (arr[v], v))
    return _build_path(g, src, dst, t0, arr, via, settled, relax)


def dijkstra_array(g, src, dst, t0):
    """Baseline: linear scan for the minimum - O(V^2)."""
    n = g.node_count()
    arr = [INF] * n
    via = [-1] * n
    done = [False] * n
    arr[src] = t0
    settled = relax = 0
    for _ in range(n):
        u, best = -1, INF
        for i in range(n):
            if not done[i] and arr[i] < best:
                u, best = i, arr[i]
        if u < 0:
            break
        done[u] = True
        settled += 1
        if u == dst:
            break
        t = arr[u]
        for eid in g.nodes[u].adj:
            v = g.edges[eid].other(u)
            if done[v]:
                continue
            tt = g.travel_time(eid, t)
            if tt != INF and t + tt < arr[v]:
                arr[v] = t + tt
                via[v] = eid
                relax += 1
    return _build_path(g, src, dst, t0, arr, via, settled, relax)


def astar_fib(g, src, dst, t0, blocked=None):
    """A* with a Fibonacci heap. f = arrival time + admissible lower bound."""
    n = g.node_count()
    arr = [INF] * n
    via = [-1] * n
    handle = [None] * n
    done = [False] * n
    pq = FibonacciHeap()
    arr[src] = t0
    handle[src] = pq.insert(t0 + g.lower_bound_minutes(src, dst), src)
    settled = relax = 0
    edges, nodes = g.edges, g.nodes
    while not pq.empty():
        _, u = pq.extract_min()
        handle[u] = None
        if done[u]:
            continue
        done[u] = True
        settled += 1
        if u == dst:
            break
        t = arr[u]
        for eid in nodes[u].adj:
            if blocked and eid in blocked:
                continue
            v = edges[eid].other(u)
            if done[v]:
                continue
            tt = g.travel_time(eid, t)
            if tt == INF:
                continue
            na = t + tt
            if na < arr[v]:
                arr[v] = na
                via[v] = eid
                relax += 1
                f = na + g.lower_bound_minutes(v, dst)
                if handle[v] is not None:
                    pq.decrease_key(handle[v], f)
                else:
                    handle[v] = pq.insert(f, v)
    return _build_path(g, src, dst, t0, arr, via, settled, relax)


def bfs_reachable(g, src, t):
    """Hop count from src to every location using roads open at time t (-1 = unreachable)."""
    hops = [-1] * g.node_count()
    hops[src] = 0
    queue = [src]
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for eid in g.nodes[u].adj:
            if not g.is_open(eid, t):
                continue
            v = g.edges[eid].other(u)
            if hops[v] < 0:
                hops[v] = hops[u] + 1
                queue.append(v)
    return hops


def components(g, t):
    """Iterative DFS. Returns (component id per node, number of components)."""
    n = g.node_count()
    comp = [-1] * n
    count = 0
    for s in range(n):
        if comp[s] >= 0:
            continue
        stack = [s]
        comp[s] = count
        while stack:
            u = stack.pop()
            for eid in g.nodes[u].adj:
                if not g.is_open(eid, t):
                    continue
                v = g.edges[eid].other(u)
                if comp[v] < 0:
                    comp[v] = count
                    stack.append(v)
        count += 1
    return comp, count


def bridges_and_cuts(g, t):
    """Tarjan's algorithm on the multigraph at time t.
    Returns (list of bridge edge ids, list of articulation-point node ids)."""
    n = g.node_count()
    disc = [-1] * n
    low = [0] * n
    is_cut = [False] * n
    bridges = []
    timer = [0]
    sys.setrecursionlimit(max(10000, 4 * n))

    def dfs(u, parent_edge):
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        children = 0
        for eid in g.nodes[u].adj:
            if eid == parent_edge or not g.is_open(eid, t):
                continue                     # skip the EDGE, not the node
            v = g.edges[eid].other(u)
            if disc[v] < 0:
                children += 1
                dfs(v, eid)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    bridges.append(eid)
                if parent_edge >= 0 and low[v] >= disc[u]:
                    is_cut[u] = True
            else:
                low[u] = min(low[u], disc[v])
        if parent_edge < 0 and children > 1:
            is_cut[u] = True

    for s in range(n):
        if disc[s] < 0:
            dfs(s, -1)
    return bridges, [i for i in range(n) if is_cut[i]]


def alternate_routes(g, src, dst, t0, k):
    """Best route + up to k-1 distinct detours (block each edge of the best route)."""
    best = dijkstra_fib(g, src, dst, t0)
    if not best.found:
        return []
    cand = []
    for e in best.edges:
        p = dijkstra_fib(g, src, dst, t0, blocked={e})
        if p.found and all(c.edges != p.edges for c in cand):
            cand.append(p)
    cand.sort(key=lambda p: p.arrive)
    return [best] + cand[:k - 1]


# ---------------------------------------------------------------------------
# Multi-stop ordering. M[i][j] = minutes from point i to point j (0 = start).
# deadline[i] is absolute minutes (INF if none).
# Objective = total travel time + late_penalty * total lateness.
# ---------------------------------------------------------------------------
def tour_cost(M, order, deadline, t0, service, late_penalty):
    t, cost, prev = t0, 0.0, 0
    for idx in order:
        leg = M[prev][idx]
        if leg == INF:
            return INF
        t += leg
        cost += leg
        if t > deadline[idx]:
            cost += late_penalty * (t - deadline[idx])
        t += service
        prev = idx
    return cost


def multi_stop(M, deadline, t0, service=5.0, late_penalty=10.0):
    """Nearest-neighbour construction followed by 2-opt improvement.
    Returns the visiting order of indices 1..m."""
    m = len(M) - 1
    order, used, cur = [], [False] * (m + 1), 0
    for _ in range(m):                                   # nearest neighbour
        best = min((j for j in range(1, m + 1) if not used[j]), key=lambda j: M[cur][j])
        used[best] = True
        order.append(best)
        cur = best
    best_cost = tour_cost(M, order, deadline, t0, service, late_penalty)
    improved = True
    while improved:                                      # 2-opt
        improved = False
        for i in range(m - 1):
            for j in range(i + 1, m):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                c = tour_cost(M, cand, deadline, t0, service, late_penalty)
                if c + 1e-9 < best_cost:
                    order, best_cost, improved = cand, c, True
    return order
