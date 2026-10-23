"""
logistics_system.py - The Intelligent Logistics Network Optimizer
-----------------------------------------------------------------------------
Ties the four data structures together:

  TemporalMultigraph g            road network, time-dependent costs, closures
  InvertedHashMap product_index   product -> warehouses that stock it
  InvertedHashMap vehicle_index   "status:X" / "type:Y" -> vehicles
  InvertedHashMap order_index     "status:X" -> orders
  FibonacciHeap   order_queue     (priority, deadline, id) -> order
  LinkedList      vehicle.pending orders loaded on a vehicle (O(1) unlink)

Case-study features implemented here:
  1 Dynamic route optimisation   plan_route / _append_leg (A*, Dijkstra)
  2 Priority-based delivery      order_queue + escalate() + cancel_order()
  3 Intelligent vehicle choice   select_vehicle()
  4 Warehouse selection          select_warehouse()
  5 Dynamic re-routing           close_road() / update_traffic()
  6 Vehicle failure recovery     breakdown()
  7 Capacity-aware delivery      capacity checks in select_vehicle()
  8 Multi-stop optimisation      plan_route() -> multi_stop()
"""
from fibonacci_heap import FibonacciHeap
from inverted_hashmap import InvertedHashMap
from linked_list import LinkedList
from temporal_multigraph import TemporalMultigraph, INF, ROAD_TYPE_NAME, clock
from algorithms import astar_fib, dijkstra_fib, multi_stop

# vehicle / order states
AVAILABLE, EN_ROUTE, BROKEN = "AVAILABLE", "EN_ROUTE", "BROKEN"
PENDING, ASSIGNED, PICKED_UP, DELIVERED, BACKORDER, CANCELLED = (
    "PENDING", "ASSIGNED", "PICKED_UP", "DELIVERED", "BACKORDER", "CANCELLED")

SERVICE_MIN = 5.0        # loading / hand-over time per stop (minutes)
ESCALATE_WINDOW = 90     # orders this close to their deadline become priority 1


class Order:
    def __init__(self, id_, customer, node, items, weight, priority, deadline):
        self.id = id_
        self.customer = customer
        self.customer_node = node
        self.items = items                  # list of (product, qty)
        self.weight = weight
        self.priority = priority            # 1 = critical ... 5 = low
        self.deadline = deadline
        self.status = PENDING
        self.warehouse = -1
        self.vehicle = -1
        self.pickup_node = -1
        self.stock_reserved = False
        self.eta = INF
        self.delivered_at = INF
        self.heap_handle = None             # for decrease_key / remove
        self.veh_handle = None              # O(1) unlink from vehicle.pending
        self.status_handle = None           # O(1) re-index on status change

    def key(self):
        # Smaller = served first: priority, then earliest deadline, then id
        return (self.priority, self.deadline, self.id)


class Warehouse:
    def __init__(self, id_, name, node):
        self.id = id_
        self.name = name
        self.node = node
        self.stock = {}
        self.idx_handle = {}                # product -> handle in product_index
        self.workload = 0


class Stop:
    def __init__(self, node, pickup, orders):
        self.node = node
        self.pickup = pickup
        self.orders = orders
        self.arrival = INF
        self.path_idx = -1
        self.done = False

    def copy(self):
        s = Stop(self.node, self.pickup, list(self.orders))
        s.arrival, s.path_idx, s.done = self.arrival, self.path_idx, self.done
        return s


class Vehicle:
    def __init__(self, id_, name, vtype, node, capacity):
        self.id = id_
        self.name = name
        self.type = vtype
        self.node = node
        self.capacity = capacity
        self.load = 0.0
        self.status = AVAILABLE
        self.pending = LinkedList()          # order ids currently on this vehicle
        self.status_handle = None
        # planned trajectory: path_nodes[i] reached at path_times[i], left at
        # path_depart[i]; path_edges[i] is the road from node i to node i+1
        self.path_nodes, self.path_edges = [node], []
        self.path_times, self.path_depart = [0.0], [0.0]
        self.stops = []
        self.progress = 0
        self.km_driven = 0.0


class LogisticsSystem:
    def __init__(self):
        self.g = TemporalMultigraph()
        self.product_index = InvertedHashMap(32)
        self.vehicle_index = InvertedHashMap(16)
        self.order_index = InvertedHashMap(16)
        self.order_queue = FibonacciHeap()
        self.warehouses = []
        self.vehicles = []
        self.orders = []
        self.unit_weight = {}
        self.now = 0.0
        self.verbose = True

    def log(self, *a):
        if self.verbose:
            print(*a)

    # ------------------------------------------------------------------ setup
    def add_warehouse(self, name, node, stock):
        w = Warehouse(len(self.warehouses), name, node)
        for p, q in stock.items():
            w.stock[p] = q
            if q > 0:
                w.idx_handle[p] = self.product_index.add(p, w.id)   # inverted index
        self.warehouses.append(w)
        return w.id

    def add_vehicle(self, name, vtype, node, capacity):
        v = Vehicle(len(self.vehicles), name, vtype, node, capacity)
        v.status_handle = self.vehicle_index.add("status:" + AVAILABLE, v.id)
        self.vehicle_index.add("type:" + vtype, v.id)
        self.vehicles.append(v)
        return v.id

    # ------------------------------------------------------------- orders (2)
    def place_order(self, customer, node, items, priority, deadline):
        weight = sum(self.unit_weight[p] * q for p, q in items)
        o = Order(len(self.orders), customer, node, items, weight, priority, deadline)
        o.heap_handle = self.order_queue.insert(o.key(), o.id)          # O(1)
        o.status_handle = self.order_index.add("status:" + PENDING, o.id)
        self.orders.append(o)
        return o.id

    def escalate(self):
        """Orders close to their deadline jump to priority 1 via decrease_key (O(1)).
        The candidates come straight from the inverted index 'status:PENDING'."""
        n = 0
        for oid in self.order_index.to_list("status:" + PENDING):
            o = self.orders[oid]
            if o.heap_handle and o.priority > 1 and o.deadline - self.now <= ESCALATE_WINDOW:
                self.log(f"   ^ escalate order #{o.id} ({o.customer}) P{o.priority} -> P1 : "
                         f"deadline {clock(o.deadline)} is within {ESCALATE_WINDOW} min")
                o.priority = 1
                self.order_queue.decrease_key(o.heap_handle, o.key())
                n += 1
        return n

    def cancel_order(self, oid):
        o = self.orders[oid]
        if o.status != PENDING or o.heap_handle is None:
            return False
        self.order_queue.remove(o.heap_handle)          # arbitrary delete from heap
        o.heap_handle = None
        self.set_order_status(o, CANCELLED)
        return True

    # ------------------------------------------------- warehouse choice (4)
    def select_warehouse(self, o):
        products = [p for p, _ in o.items]
        cands = self.product_index.intersect(products)                # inverted index
        self.log(f"   warehouses stocking {{{', '.join(products)}}}: {len(cands)} candidate(s)")
        best, best_score = -1, INF
        for wid in cands:
            w = self.warehouses[wid]
            if any(w.stock.get(p, 0) < q for p, q in o.items):
                self.log(f"     - {w.name:<18} insufficient quantity")
                continue
            p = astar_fib(self.g, w.node, o.customer_node, self.now)
            score = p.minutes + 4.0 * w.workload                       # distance + workload
            self.log(f"     - {w.name:<18} {p.minutes:5.1f} min to customer, workload {w.workload} "
                     f"-> score {score:.1f}")
            if score < best_score:
                best, best_score = wid, score
        return best

    def reserve_stock(self, o, w):
        for p, q in o.items:
            w.stock[p] -= q
            if w.stock[p] == 0:                       # drop from index in O(1)
                self.product_index.remove(p, w.idx_handle.pop(p))
                self.log(f"     ! {w.name} is now out of '{p}' -> removed from product index")
        o.stock_reserved = True

    def release_stock(self, o):
        if not o.stock_reserved or o.warehouse < 0:
            return
        w = self.warehouses[o.warehouse]
        for p, q in o.items:
            if w.stock[p] == 0:
                w.idx_handle[p] = self.product_index.add(p, w.id)
            w.stock[p] += q
        o.stock_reserved = False

    # ------------------------------------ vehicle choice + capacity (3, 7)
    def select_vehicle(self, o):
        to_cust = astar_fib(self.g, o.pickup_node, o.customer_node, self.now)
        best = best_feasible = -1
        best_score = best_feas_score = INF
        avail = self.vehicle_index.to_list("status:" + AVAILABLE)     # inverted index
        self.log(f"   available vehicles: {len(avail)}")
        for vid in avail:
            v = self.vehicles[vid]
            if v.load + o.weight > v.capacity:                         # capacity-aware
                self.log(f"     - {v.name:<9} load {v.load:.1f} + {o.weight:.1f} kg > capacity "
                         f"{v.capacity:.0f} kg  (skipped)")
                continue
            to_pick = astar_fib(self.g, v.node, o.pickup_node, self.now)
            if not to_pick.found:
                continue
            score = to_pick.minutes + 8.0 * len(v.pending)             # distance + balance
            est = to_pick.arrive + SERVICE_MIN * (1 + len(v.pending)) + to_cust.minutes
            feasible = est <= o.deadline
            self.log(f"     - {v.name:<9} {to_pick.minutes:5.1f} min to pickup, {len(v.pending)} queued, "
                     f"est. delivery {clock(est)} {'(on time)' if feasible else '(LATE)'} "
                     f"-> score {score:.1f}")
            if score < best_score:
                best, best_score = vid, score
            if feasible and score < best_feas_score:
                best_feasible, best_feas_score = vid, score
        return best_feasible if best_feasible >= 0 else best

    def dispatch(self):
        """Pull every order from the Fibonacci heap in priority order and assign it."""
        self.escalate()
        deferred = []
        while not self.order_queue.empty():
            key, oid = self.order_queue.extract_min()
            o = self.orders[oid]
            o.heap_handle = None
            items = ", ".join(f"{q}x {p}" for p, q in o.items)
            self.log(f"\n>> Order #{o.id:<2} {o.customer:<13} P{key[0]}  deadline {clock(o.deadline)}  "
                     f"{o.weight:.1f} kg  [{items}]")
            if o.pickup_node < 0:
                wid = self.select_warehouse(o)
                if wid < 0:
                    self.log("   x no warehouse can fulfil it -> BACKORDER")
                    self.set_order_status(o, BACKORDER)
                    continue
                o.warehouse = wid
                o.pickup_node = self.warehouses[wid].node
                self.reserve_stock(o, self.warehouses[wid])
                self.log(f"   => warehouse: {self.warehouses[wid].name}")
            else:
                self.log(f"   goods are on a broken vehicle at {self.g.nodes[o.pickup_node].name}"
                         " -> pick up there")
            vid = self.select_vehicle(o)
            if vid < 0:
                self.log("   x no vehicle with spare capacity -> retry next round")
                deferred.append(oid)
                continue
            self.assign(o, self.vehicles[vid])
            v = self.vehicles[vid]
            self.log(f"   => vehicle: {v.name} (load now {v.load:.1f} / {v.capacity:.0f} kg)")
        for oid in deferred:
            o = self.orders[oid]
            o.heap_handle = self.order_queue.insert(o.key(), o.id)

    def assign(self, o, v):
        o.vehicle = v.id
        o.veh_handle = v.pending.push_back(o.id)
        v.load += o.weight
        if self._from_warehouse(o):
            self.warehouses[o.warehouse].workload += 1
        self.set_order_status(o, ASSIGNED)

    # -------------------------------------------- multi-stop planning (1, 8)
    def plan_all_routes(self):
        for v in self.vehicles:
            if v.status == AVAILABLE and v.pending:
                self.plan_route(v)

    def plan_route(self, v):
        # ---- collect stops: pickups first (unique nodes), then drops ----
        picks, drops = [], []
        for oid in v.pending:
            o = self.orders[oid]
            if o.status == ASSIGNED:
                self._add_to_stops(picks, o.pickup_node, True, oid)
            self._add_to_stops(drops, o.customer_node, False, oid)
        # ---- travel-time matrix: one Fibonacci-heap Dijkstra per point ----
        pts = [v.node] + [s.node for s in picks] + [s.node for s in drops]
        M = []
        for p in pts:
            arr = []
            dijkstra_fib(self.g, p, -1, self.now, all_arrival=arr)
            M.append([arr[q] - self.now for q in pts])
        # ---- pickups: nearest neighbour from the vehicle ----
        ordered, cur, t = [], 0, self.now
        used = [False] * len(picks)
        for _ in picks:
            bi = min((i for i in range(len(picks)) if not used[i]), key=lambda i: M[cur][1 + i])
            used[bi] = True
            t += M[cur][1 + bi] + SERVICE_MIN
            cur = 1 + bi
            ordered.append(picks[bi])
        # ---- drops: nearest neighbour + 2-opt with deadline penalty ----
        off = 1 + len(picks)
        idx = [cur] + [off + i for i in range(len(drops))]
        DM = [[M[a][b] for b in idx] for a in idx]
        dl = [INF] + [min(self.orders[oid].deadline for oid in s.orders) for s in drops]
        for s in multi_stop(DM, dl, t, SERVICE_MIN):
            ordered.append(drops[s - 1])
        # ---- fresh trajectory starting at the vehicle's location ----
        v.path_nodes, v.path_times, v.path_depart, v.path_edges = [v.node], [self.now], [self.now], []
        v.progress = 0
        v.stops = []
        self._build_trajectory(v, ordered)
        self.set_vehicle_status(v, EN_ROUTE)
        if self.verbose:
            self.print_plan(v)

    # --------------------------------------------------------- simulation clock
    def advance_to(self, t):
        self.now = t
        for v in self.vehicles:
            if v.status != EN_ROUTE:
                continue
            while v.progress + 1 < len(v.path_nodes) and v.path_times[v.progress + 1] <= t:
                v.km_driven += self.g.edges[v.path_edges[v.progress]].km
                v.progress += 1
            v.node = v.path_nodes[v.progress]
            for s in v.stops:
                if s.done or s.path_idx < 0 or s.path_idx > v.progress:
                    continue
                s.done = True
                for oid in s.orders:
                    o = self.orders[oid]
                    if s.pickup:
                        if o.status == ASSIGNED:
                            if self._from_warehouse(o):
                                self.warehouses[o.warehouse].workload -= 1
                            self.set_order_status(o, PICKED_UP)
                    elif o.status == PICKED_UP:
                        self.set_order_status(o, DELIVERED)
                        o.delivered_at = s.arrival
                        v.pending.remove(o.veh_handle)          # O(1) via handle
                        o.veh_handle = None
                        v.load -= o.weight
            if all(s.done for s in v.stops) and t >= v.path_depart[-1]:
                v.stops = []
                self.set_vehicle_status(v, AVAILABLE)

    # ------------------------------------------------ dynamic re-routing (5)
    def close_road(self, edge_id, start, end):
        """Close road during [start, end). Vehicles whose remaining plan would ENTER
        the road inside that window are re-routed from where they are."""
        self.g.add_closure(edge_id, start, end)
        e = self.g.edges[edge_id]
        print(f"   Road CLOSED: {e.name} ({self.g.nodes[e.u].name} <-> {self.g.nodes[e.v].name}, "
              f"{ROAD_TYPE_NAME[e.type]}) from {clock(start)} to {clock(end)}")
        for v in self.vehicles:
            if v.status != EN_ROUTE:
                continue
            for i in range(v.progress, len(v.path_edges)):
                d = v.path_depart[i]
                if v.path_edges[i] == edge_id and d >= self.now and start <= d < end:
                    self.reroute(v, "road closure")
                    break

    def update_traffic(self, edge_id, factor):
        """Live traffic report: congestion factor on one road; affected vehicles re-plan."""
        self.g.set_congestion(edge_id, factor)
        e = self.g.edges[edge_id]
        print(f"   TRAFFIC x{factor:.1f} on {e.name} ({self.g.nodes[e.u].name} <-> "
              f"{self.g.nodes[e.v].name})")
        for v in self.vehicles:
            if v.status != EN_ROUTE:
                continue
            for i in range(v.progress, len(v.path_edges)):
                if v.path_edges[i] == edge_id and v.path_depart[i] >= self.now:
                    self.reroute(v, "heavy traffic")
                    break

    def reroute(self, v, why):
        old_end = v.path_times[-1]
        s = v.progress
        start_time = max(self.now, v.path_depart[s])
        if v.path_depart[s] < self.now and s + 1 < len(v.path_nodes):  # mid-road: finish it first
            s += 1
            start_time = v.path_times[s]
        old_roads = self.roads_ahead(v, s)
        remaining = []
        for st in v.stops:
            if not st.done:
                c = st.copy()
                c.path_idx = -1
                remaining.append(c)
        del v.path_nodes[s + 1:], v.path_times[s + 1:], v.path_depart[s + 1:], v.path_edges[s:]
        v.path_depart[s] = start_time
        v.stops = [st for st in v.stops if st.done]
        self._build_trajectory(v, remaining)
        new_roads = self.roads_ahead(v, s)
        print(f"   >> {v.name} re-routed ({why}) at {clock(self.now)} - plan changes from "
              f"{self.g.nodes[v.path_nodes[s]].name} ({clock(start_time)})")
        print(f"      before: {old_roads}   finish {clock(old_end)}")
        note = "  (same roads are still fastest - ETA updated)" if new_roads == old_roads else ""
        print(f"      after : {new_roads}   finish {clock(v.path_times[-1])}{note}")

    # ------------------------------------------- vehicle failure recovery (6)
    def breakdown(self, vid):
        v = self.vehicles[vid]
        print(f"   !! {v.name} BROKE DOWN at {self.g.nodes[v.node].name} ({clock(self.now)}) "
              f"with {len(v.pending)} undelivered order(s)")
        rescue = FibonacciHeap()                               # small temporary heap
        while v.pending:
            oid = v.pending.pop_front()
            o = self.orders[oid]
            o.veh_handle, o.vehicle = None, -1
            if o.status == PICKED_UP:
                o.pickup_node = v.node                         # goods are on the truck
                print(f"      order #{o.id} ({o.customer}): goods on board -> rescue pickup at "
                      f"{self.g.nodes[v.node].name}")
            else:
                if self._from_warehouse(o):
                    self.warehouses[o.warehouse].workload -= 1
                self.release_stock(o)
                o.warehouse, o.pickup_node = -1, -1
                print(f"      order #{o.id} ({o.customer}): not picked up yet -> stock released, "
                      "re-select warehouse")
            if o.priority > 1:
                o.priority -= 1                                # delayed orders gain urgency
            self.set_order_status(o, PENDING)
            o.heap_handle = rescue.insert(o.key(), o.id)
        before = len(self.order_queue)
        self.order_queue.merge(rescue)                         # O(1) meld into main queue
        print(f"      Fibonacci-heap MERGE: main queue {before} -> {len(self.order_queue)} orders (O(1))")
        v.load = 0.0
        v.stops = []
        v.path_nodes, v.path_times, v.path_depart, v.path_edges = [v.node], [self.now], [self.now], []
        v.progress = 0
        self.set_vehicle_status(v, BROKEN)

    # --------------------------------------------------------------- reporting
    def print_fleet(self):
        print(f"   {'Vehicle':<9} {'Type':<6} {'Status':<10} {'Location':<16} {'Load(kg)':>10} {'Orders':>8}")
        for v in self.vehicles:
            load = f"{v.load:5.1f}/{v.capacity:<4.0f}"
            print(f"   {v.name:<9} {v.type:<6} {v.status:<10} {self.g.nodes[v.node].name:<16} "
                  f"{load:>10} {len(v.pending):>8}")

    def print_orders(self):
        print(f"   {'#':<3} {'Customer':<13} {'P':<3} {'Deadline':<9} {'Status':<10} {'Vehicle':<9} "
              f"{'ETA':<8} {'Done':<8} On time?")
        for o in self.orders:
            ok = "-"
            if o.status == DELIVERED:
                ok = "yes" if o.delivered_at <= o.deadline else "LATE"
            veh = self.vehicles[o.vehicle].name if o.vehicle >= 0 else "-"
            print(f"   {o.id:<3} {o.customer:<13} {o.priority:<3} {clock(o.deadline):<9} {o.status:<10} "
                  f"{veh:<9} {clock(o.eta):<8} {clock(o.delivered_at):<8} {ok}")

    def print_plan(self, v):
        print(f"\n   {v.name} plan ({len(v.stops)} stops, start {clock(v.path_times[0])} from "
              f"{self.g.nodes[v.path_nodes[0]].name}):")
        for s in v.stops:
            if s.done:
                continue
            ids = " ".join(f"#{oid}" for oid in s.orders)
            print(f"     {clock(s.arrival)}  {'PICKUP' if s.pickup else 'DROP':<6} "
                  f"{self.g.nodes[s.node].name:<16} orders {ids}")
        print(f"     roads: {self.roads_ahead(v)}")

    def roads_ahead(self, v, start=None):
        out, last = [], -1
        for i in range(v.progress if start is None else start, len(v.path_edges)):
            e = v.path_edges[i]
            if e != last:
                out.append(self.g.edges[e].name)
                last = e
        return " > ".join(out) if out else "(none)"

    def set_order_status(self, o, status):
        self.order_index.remove("status:" + o.status, o.status_handle)
        o.status = status
        o.status_handle = self.order_index.add("status:" + status, o.id)

    def set_vehicle_status(self, v, status):
        self.vehicle_index.remove("status:" + v.status, v.status_handle)
        v.status = status
        v.status_handle = self.vehicle_index.add("status:" + status, v.id)

    # ----------------------------------------------------------------- helpers
    def _from_warehouse(self, o):
        return o.warehouse >= 0 and o.pickup_node == self.warehouses[o.warehouse].node

    @staticmethod
    def _add_to_stops(stops, node, pickup, oid):
        for s in stops:
            if s.node == node:
                s.orders.append(oid)
                return
        stops.append(Stop(node, pickup, [oid]))

    def _append_leg(self, v, to, t):
        """Time-dependent A* leg, appended after the current last node."""
        frm = v.path_nodes[-1]
        v.path_depart[-1] = t
        if frm == to:
            return t
        p = astar_fib(self.g, frm, to, t)
        if not p.found:
            return INF
        for k in range(1, len(p.nodes)):
            v.path_edges.append(p.edges[k - 1])
            v.path_nodes.append(p.nodes[k])
            v.path_times.append(p.times[k])
            v.path_depart.append(p.times[k])
        return p.arrive

    def _build_trajectory(self, v, ordered):
        t = v.path_depart[-1]
        for s in ordered:
            arr = self._append_leg(v, s.node, t)
            if arr == INF:
                print(f"     ! {v.name} cannot reach {self.g.nodes[s.node].name} right now (network cut)")
                continue
            s.arrival = arr
            s.path_idx = len(v.path_nodes) - 1
            t = arr + SERVICE_MIN
            v.path_depart[-1] = t
            if not s.pickup:
                for oid in s.orders:
                    self.orders[oid].eta = arr
            v.stops.append(s)
