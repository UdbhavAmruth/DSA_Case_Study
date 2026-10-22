# Intelligent Logistics Network Optimization & Dynamic Route Planning System (Python)

A pure-Python 3 implementation of the DSA case study. It needs **no external libraries**; only the standard library is used.
It is built on four advanced data structures, all **written from scratch**. Python's `dict`, `heapq` and so on are not used for them; `heapq` appears only as the comparison baseline in the benchmark.

| Data structure | File | Main job in the system |
|---|---|---|
| **Doubly Linked List** (with O(1) handles) | `linked_list.py` | posting lists, adjacency lists, road-closure windows, each vehicle's pending orders |
| **Inverted HashMap** | `inverted_hashmap.py` | product → warehouses, status → vehicles, status → orders |
| **Temporal Multigraph** | `temporal_multigraph.py` | road network with parallel roads, rush-hour traffic and timed closures |
| **Fibonacci Heap** | `fibonacci_heap.py` | Dijkstra/A* priority queue **and** the global delivery-order queue |

---

## 1. How to run

Requires Python 3.8 or newer. Check with `python --version`.

```bash
python main.py          # full demo of all 10 features   (output saved in demo_output.txt)
python tests.py         # 8 unit tests for the four data structures
python benchmark.py     # feature 10 – performance analysis, ~30 s (output in benchmark_output.txt)
python benchmark.py --quick   # smaller sizes, ~5 s
```
On Mac/Linux, use `python3` instead of `python` if needed. Run the commands from inside the project folder.

To save your own output, run `python main.py > my_output.txt`.

## 2. Project structure

```
LogisticsDSA_Python/
├── linked_list.py          doubly linked list, O(1) remove via node handle, O(1) splice
├── inverted_hashmap.py     own chained hash table (FNV-1a, auto-rehash) of key -> LinkedList of ids
├── fibonacci_heap.py       insert/merge/decrease_key O(1), extract_min/remove O(log n) amortised
├── temporal_multigraph.py  locations, parallel roads, travel_time(edge, t), closures
├── algorithms.py           Dijkstra (3 variants), A*, BFS, DFS, Tarjan, alternate routes, multi-stop
├── logistics_system.py     orders, warehouses, vehicles – the complete dispatcher
├── main.py                 demo scenario (19-location city, 3 warehouses, 6 vehicles, 12 orders)
├── tests.py                unit tests (unittest)
├── benchmark.py            performance comparison
├── demo_output.txt
└── benchmark_output.txt
```

Suggested reading order: `linked_list` → `inverted_hashmap` → `fibonacci_heap` → `temporal_multigraph` → `algorithms` → `logistics_system` → `main`. Each file starts with a docstring explaining what it does and why.

## 3. Which data structure solves which feature

| # | Case-study feature | How it is solved | Data structures used |
|---|---|---|---|
| 1 | Dynamic route optimisation | Time-dependent **Dijkstra** and **A\*** (straight-line heuristic) | Temporal Multigraph + Fibonacci heap |
| 2 | Priority-based delivery | Orders keyed by (priority, deadline, id). Near-deadline orders are escalated with `decrease_key`; cancelled orders are pulled out with `remove` | Fibonacci heap, Inverted HashMap (`status:PENDING`) |
| 3 | Intelligent vehicle assignment | Score = travel time to pickup + load-balancing penalty, with a deadline feasibility check | Inverted HashMap (`status:AVAILABLE`), A* |
| 4 | Warehouse selection | `intersect(products of the order)` → only warehouses that stock **all** items, scored by travel time + workload. A warehouse that runs out is unlinked from the index in O(1) | Inverted HashMap + linked-list handles |
| 5 | Dynamic re-routing | Closures are time windows on an edge; traffic is a congestion factor. Only vehicles whose **future** path enters the affected road are re-planned, from where they currently are | Temporal Multigraph |
| 6 | Vehicle failure recovery | The broken vehicle's orders go into a small heap that is **merged** into the main queue in O(1). Goods already on board get a rescue pickup at the breakdown point | Fibonacci heap `merge`, linked list |
| 7 | Capacity-aware delivery | `load + weight ≤ capacity` checked before every assignment; load drops as each order is delivered | Linked list of pending orders |
| 8 | Multi-stop optimisation | Travel-time matrix (one Dijkstra per stop) → nearest-neighbour → **2-opt**, objective = travel time + 10 × lateness | Fibonacci-heap Dijkstra |
| 9 | Network analysis | BFS reachability, DFS components, **Tarjan bridges & articulation points**, alternate routes, what-if closures | Temporal Multigraph |
| 10 | Performance analysis | `benchmark.py`; see section 6 | all |

---

## 4. Why these data structures instead of the basic ones

### 4.1 Doubly Linked List with node handles
**Basic alternative:** Python `list`.

The system keeps removing items **from the middle** of collections:
* a delivered order leaves its vehicle's pending list
* a warehouse that runs out of a product leaves that product's posting list
* a vehicle that changes status leaves the `status:AVAILABLE` list

With a Python list, `list.remove(x)` is an O(n) search plus an O(n) shift. Our `push_back()` returns the **node object** (a *handle*), and the owner stores it (`order.veh_handle`, `warehouse.idx_handle`, `vehicle.status_handle`). Later, `remove(handle)` unlinks that node in **O(1)** with no search. `splice()` moves a whole list in O(1).

The linked list is also the building block of the other three structures: posting lists, adjacency lists, and the circular sibling lists inside the Fibonacci heap.

### 4.2 Inverted HashMap
**Basic alternatives:** a forward map `warehouse → stock`, or the BST/AVL suggested in the case study.

A forward map answers *"what does warehouse 7 stock?"*. The dispatcher asks the reverse: *"which warehouses stock a laptop **and** a phone?"*. With a forward map or a BST keyed by warehouse, you have to visit **every** warehouse (O(W)). An inverted index stores the answer directly:

```
"laptop"           -> [WH-Peenya] <-> [WH-Whitefield]
"fridge"           -> [WH-Peenya] <-> [WH-ElectronicCity]
"status:AVAILABLE" -> [Van-01] <-> [Bike-01] <-> ...
```

* Key lookup is **O(1) average** (hash) instead of O(log n) (BST), and it returns only the matching ids.
* `intersect([k1, k2, ...])` finds warehouses that can fill a multi-item order in O(sum of posting lengths).
* The same class indexes vehicles (`status:`, `type:`) and orders (`status:`).
* Deleting a posting is O(1) because we keep the linked-list handle.

It is our own hash table: separate chaining, FNV-1a hash, power-of-two bucket count, rehash at load factor 0.75. Rehashing re-links the entries rather than copying them, so stored handles stay valid.

### 4.3 Temporal Multigraph
**Basic alternative:** a simple weighted graph (`adj[u] = [(v, w)]` or an adjacency matrix).

1. **Multi-graph: parallel roads.** Two places can be joined by more than one road, for example an elevated expressway **and** a city road between Silk Board and Electronic City. A simple graph keeps one weight per pair. Here every road is its own edge with its own id, speed, type, traffic and closures, and the route says **which** road to take.
2. **Temporal: costs depend on time.** `travel_time(edge, t) = base × rush_hour_profile[type](t) × congestion`, and edges can be closed for windows `[start, end)`.

What the demo shows:
* Electronic City → Hebbal at **08:30** uses *Hosur Rd (S)*; at **14:00** it uses the *E-City Elevated Expwy*.
* The 09:00–12:00 closure only affects trips entering the road in that window.
* **Tarjan on a multigraph** skips the parent *edge id*, not the parent node. So Silk Board–Electronic City (two parallel roads) is correctly **not** a bridge, while Hebbal–Yelahanka (one road) is. A simple graph would flag both.

### 4.4 Fibonacci Heap
**Basic alternatives:** binary heap (`heapq`), sorted list, BST.

| Operation | Binary heap (`heapq`) | Fibonacci heap |
|---|---|---|
| insert | O(log n) | **O(1)** |
| find-min | O(1) | O(1) |
| extract-min | O(log n) | O(log n) amortised |
| decrease-key | **not supported** | **O(1)** amortised |
| delete arbitrary | not supported | O(log n) amortised |
| merge two heaps | O(n) | **O(1)** |

It is used in two places:
1. **Dijkstra / A\*:** total cost O(E + V log V) instead of O((V+E) log V).
2. **The delivery-order queue**, which needs exactly the three operations `heapq` lacks:
   * an order nears its deadline → `decrease_key` to priority 1 (escalation)
   * a customer cancels → `remove(handle)`
   * a vehicle breaks down → its orders form a small heap that is `merge`d into the main queue in O(1)

---

## 5. Complexity summary

| Operation in the system | Cost |
|---|---|
| Place order | O(1) heap insert + O(1) index insert |
| Escalate / cancel order | O(1) / O(log n) amortised |
| Find warehouses stocking all items | O(Σ posting lengths) |
| Find available vehicles | O(1) lookup |
| Mark delivered / change status | O(1) using handles |
| Route between two points | O(E + V log V) |
| Multi-stop plan for m stops | m × O(E + V log V), then 2-opt O(m²) per pass |
| Breakdown recovery (k orders) | O(k) + O(1) merge |
| Bridges / articulation points | O(V + E) |

---

## 6. Performance analysis (feature 10)

Full output is in `benchmark_output.txt`. Representative numbers:

**Shortest path on a sparse city grid (V = 10 000, E ≈ 22 800):**

| Algorithm | ms / query | nodes settled |
|---|---|---|
| Dijkstra + array | skipped (O(V²); already 93 ms at V = 2 500) | – |
| Dijkstra + binary heap (`heapq`) | 20 | 4 976 |
| Dijkstra + Fibonacci heap | 60 | 4 976 |
| **A\* + Fibonacci heap** | 47 | **3 578** |

All algorithms return the same route cost on every query.

**How to explain these results in the viva:**

1. **Any heap beats the plain array.** At V = 2 500 the heap versions are 13–35× faster, and the array version gets worse quadratically.
2. **A\* settles about 28% fewer nodes** than Dijkstra for the same answer.
3. **`heapq` is faster in wall-clock time than our Fibonacci heap.** There are two reasons:
   * `heapq` is written in C, while our heap is pure Python.
   * Road networks are sparse (E ≈ 2.3 V), so there are few decrease-keys for the Fibonacci heap to save.

   On the **dense** network (E ≈ 140 V) the two run equal (140 ms each), even though one is Python and the other is C. That is where the Fibonacci heap's O(1) decrease-key starts to pay off.
4. **The Fibonacci heap was chosen for its operations, not raw speed.** The order queue needs decrease-key, delete and merge. `heapq` can only fake decrease-key by pushing duplicates, and it cannot cancel or merge at all.
5. **Inverted HashMap vs others** (2 000 warehouses, 20 000 queries):
   * It is about **100× faster than a linear scan** for single-product lookups (36 ms vs 3 538 ms) and about 6× faster for two-product intersections (446 ms vs 2 901 ms).
   * Python's built-in `dict` and `bisect` (both written in C) beat our pure-Python version on constant factors. That is a C-vs-Python effect, not an algorithmic one; we hand-wrote the table because the project asks us to build the structure ourselves.
6. A sorted list (`bisect.insort`) as a priority queue is the slowest option: about 30× slower than `heapq` at N = 50 000, because every insert and delete shifts the list (O(n)).

### Limitations / possible extensions
* Multi-stop optimisation is a heuristic (NN + 2-opt). The exact problem (TSP with time windows) is NP-hard.
* The multi-stop travel-time matrix is computed at departure time. The final itinerary is then re-timed leg by leg with true time-dependent A\*.
* A vehicle that is already en route does not accept new orders. Rescue orders go to idle vehicles.
* Time-dependent Dijkstra is exact under the FIFO property. The interpolated traffic profile is designed to keep it.

---

## 7. Likely viva questions

* **Why not `heapq`?** It has no decrease-key, no delete and no merge, and we need all three for escalation, cancellation and breakdown recovery.
* **Why an inverted index and not an AVL tree for warehouses?** An AVL tree keyed by warehouse cannot answer "who stocks X?" without visiting every node. Keyed by product it costs O(log P), versus O(1) average for the hash.
* **What makes the graph "temporal"?** Edge cost is a function of entry time (`travel_time(e, t)`) and edges have closure windows, so the same query gives different routes at different times.
* **What makes it a "multigraph"?** Several edges can join the same two vertices. This matters for routing (choosing the right road) and for bridge detection (parallel roads give redundancy).
* **Why is A\* admissible?** h = straight-line km ÷ max speed × smallest traffic multiplier. Every road is at least as long as the straight line, no road is faster than the max speed, and no multiplier is smaller than the minimum, so h never overestimates.
* **Why is the Python Fibonacci heap slower than heapq?** heapq is C code and road graphs are sparse. Big-O hides constant factors, but the operations it supports are what we needed.
