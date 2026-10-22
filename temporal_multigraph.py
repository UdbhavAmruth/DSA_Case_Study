"""
temporal_multigraph.py - Road network whose edges change with time
-----------------------------------------------------------------------------
MULTI-graph : two locations may be joined by several parallel roads
              (e.g. an expressway AND a city road between the same hubs).
              Each road is its own edge with its own id, length, speed,
              type, traffic and closures. A simple graph (adj[u][v] = w)
              would be forced to keep only one of them.

TEMPORAL    : the cost of an edge depends on WHEN you enter it.
              travel_time(edge, t) = base * rush_hour_profile[type](t) * congestion
              and an edge can be closed during time windows [start, end).
              So the best route at 09:00 (rush hour, expressway jammed) can
              legitimately differ from the best route at 14:00 - and a road
              closure scheduled for 10:00-12:00 only affects trips in that
              window. Static weights cannot model any of this.

Storage     : adjacency list - every location keeps a LinkedList of incident
              edge ids; every edge keeps a LinkedList of closure windows.
Time unit   : minutes since 00:00 of the simulation day (e.g. 540 = 09:00).
"""
import math
from linked_list import LinkedList

INF = math.inf

EXPRESSWAY, ARTERIAL, LOCAL = 0, 1, 2
ROAD_TYPE_NAME = {EXPRESSWAY: "Expressway", ARTERIAL: "Arterial", LOCAL: "Local"}

# Hourly multipliers per road type (index = hour 0..23).
# Expressways suffer most at rush hour; local roads least.
PROFILE = [
    # 0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20   21   22   23
    [0.9, 0.9, 0.9, 0.9, 0.9, 1.0, 1.4, 2.6, 4.0, 3.6, 1.8, 1.2, 1.1, 1.1, 1.0, 1.1, 1.6, 3.4, 4.0, 2.6, 1.5, 1.1, 1.0, 0.9],
    [0.9, 0.9, 0.9, 0.9, 0.9, 1.0, 1.2, 1.7, 2.0, 1.9, 1.4, 1.2, 1.2, 1.1, 1.1, 1.2, 1.4, 1.8, 2.0, 1.7, 1.3, 1.1, 1.0, 0.9],
    [0.9, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0, 1.2, 1.3, 1.3, 1.2, 1.1, 1.1, 1.1, 1.1, 1.1, 1.2, 1.3, 1.3, 1.2, 1.1, 1.0, 1.0, 0.9],
]
MIN_PROFILE = 0.9     # smallest multiplier above (used by the A* heuristic)
MAX_SPEED = 100.0     # fastest road speed allowed (km/h)


def profile(road_type, minutes):
    """Rush-hour multiplier, linearly interpolated so travel time is continuous."""
    h = (minutes / 60.0) % 24.0
    h0 = int(h)
    h1 = (h0 + 1) % 24
    f = h - h0
    row = PROFILE[road_type]
    return row[h0] * (1 - f) + row[h1] * f


def clock(minutes):
    if minutes == INF or minutes is None:
        return "--:--"
    m = int(round(minutes))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


class Edge:
    __slots__ = ("id", "u", "v", "name", "km", "speed", "type", "congestion", "closures")

    def __init__(self, id_, u, v, name, km, speed, road_type):
        self.id = id_
        self.u, self.v = u, v
        self.name = name
        self.km = km
        self.speed = speed
        self.type = road_type
        self.congestion = 1.0          # live traffic factor (>= 1.0)
        self.closures = LinkedList()   # (start, end) windows when unusable

    def other(self, x):
        return self.v if x == self.u else self.u


class Location:
    __slots__ = ("id", "name", "x", "y", "adj")

    def __init__(self, id_, name, x, y):
        self.id = id_
        self.name = name
        self.x, self.y = x, y          # coordinates in km (used by A*)
        self.adj = LinkedList()        # incident edge ids (parallel edges allowed)


class TemporalMultigraph:
    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_location(self, name, x, y):
        loc = Location(len(self.nodes), name, x, y)
        self.nodes.append(loc)
        return loc.id

    def add_road(self, u, v, name, road_type, speed, km=None):
        """Bidirectional road. Parallel roads between the same pair are allowed.
        km is never allowed below the straight-line distance (keeps A* admissible)."""
        straight = self.euclid(u, v)
        if km is None:
            km = straight * 1.15
        km = max(km, straight)
        speed = min(speed, MAX_SPEED)
        e = Edge(len(self.edges), u, v, name, km, speed, road_type)
        self.edges.append(e)
        self.nodes[u].adj.push_back(e.id)
        self.nodes[v].adj.push_back(e.id)
        return e.id

    # ---------------------------------------------------- temporal behaviour
    def is_open(self, edge_id, t):
        for start, end in self.edges[edge_id].closures:
            if start <= t < end:
                return False
        return True

    def travel_time(self, edge_id, t):
        """Minutes needed to traverse the edge when entering it at time t."""
        e = self.edges[edge_id]
        if e.closures and not self.is_open(edge_id, t):
            return INF
        base = e.km / e.speed * 60.0
        return base * profile(e.type, t) * e.congestion

    def add_closure(self, edge_id, start, end):
        self.edges[edge_id].closures.push_back((start, end))

    def reopen(self, edge_id):
        self.edges[edge_id].closures.clear()

    def set_congestion(self, edge_id, factor):
        self.edges[edge_id].congestion = max(1.0, factor)

    def lower_bound_minutes(self, a, b):
        """Admissible A* heuristic: straight line at max speed, best-case traffic."""
        return self.euclid(a, b) / MAX_SPEED * 60.0 * MIN_PROFILE

    def euclid(self, a, b):
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na.x - nb.x, na.y - nb.y)

    def multiplicity(self, u, v):
        """Number of parallel roads between u and v."""
        return sum(1 for eid in self.nodes[u].adj if self.edges[eid].other(u) == v)

    def node_count(self):
        return len(self.nodes)

    def edge_count(self):
        return len(self.edges)
