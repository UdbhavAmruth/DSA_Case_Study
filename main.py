"""
main.py - End-to-end demonstration of all 10 case-study features
Run:  python main.py
"""
from logistics_system import LogisticsSystem, EN_ROUTE, DELIVERED
from temporal_multigraph import EXPRESSWAY, ARTERIAL, LOCAL, clock
from algorithms import (dijkstra_fib, astar_fib, bfs_reachable, components,
                        bridges_and_cuts, alternate_routes)


def banner(title):
    print("\n" + "=" * 76)
    print("  " + title)
    print("=" * 76)


def T(h, m=0):
    return h * 60.0 + m


def print_path(g, p):
    if not p.found:
        print("      (no route)")
        return
    s = "      " + g.nodes[p.nodes[0]].name
    for i, e in enumerate(p.edges):
        s += f" -[{g.edges[e].name}]-> {g.nodes[p.nodes[i + 1]].name}"
    print(s)
    print(f"      depart {clock(p.depart)}  arrive {clock(p.arrive)}  "
          f"({p.minutes:.1f} min, {p.settled} nodes settled)")


def main():
    sys_ = LogisticsSystem()
    g = sys_.g

    # ------------------------------------------------------------------ city
    # Coordinates are in km (approximate layout of a large Indian city).
    majestic = g.add_location("Majestic", 0, 0)
    rajaji = g.add_location("Rajajinagar", -3, 1.5)
    mallesh = g.add_location("Malleshwaram", -1, 3)
    peenya = g.add_location("Peenya", -6, 6)
    yeshwant = g.add_location("Yeshwanthpur", -3, 5)
    hebbal = g.add_location("Hebbal", 2, 7)
    yelahan = g.add_location("Yelahanka", 3, 15)
    mgroad = g.add_location("MG Road", 3, 0)
    indira = g.add_location("Indiranagar", 6, 0.5)
    krpuram = g.add_location("KR Puram", 11, 3)
    white = g.add_location("Whitefield", 17, 1)
    marath = g.add_location("Marathahalli", 11, -2)
    kora = g.add_location("Koramangala", 4, -4)
    hsr = g.add_location("HSR Layout", 6, -7)
    silk = g.add_location("Silk Board", 4, -7.5)
    ecity = g.add_location("Electronic City", 6, -16)
    btm = g.add_location("BTM Layout", 2, -6)
    jaya = g.add_location("Jayanagar", 0, -5)
    banash = g.add_location("Banashankari", -2, -8)

    EXP, ART, LOC = 80, 45, 28
    roads = [
        (majestic, rajaji, "Chord Rd", ARTERIAL, ART),
        (majestic, mallesh, "Sampige Rd", LOCAL, LOC),
        (rajaji, yeshwant, "West of Chord Rd", ARTERIAL, ART),
        (mallesh, yeshwant, "Malleshwaram 18th Cross", LOCAL, LOC),
        (yeshwant, peenya, "Tumkur Rd", ARTERIAL, ART),                  # parallel pair
        (yeshwant, peenya, "Peenya Elevated Expwy", EXPRESSWAY, EXP),    # parallel pair
        (peenya, rajaji, "Peenya Industrial Rd", LOCAL, LOC),
        (yeshwant, hebbal, "Outer Ring Rd (N)", ARTERIAL, ART),
        (mallesh, hebbal, "Sankey Rd", LOCAL, LOC),
        (hebbal, mgroad, "Hebbal Flyover Expwy", EXPRESSWAY, EXP),       # parallel pair
        (hebbal, mgroad, "Bellary Rd", ARTERIAL, ART),                   # parallel pair
        (hebbal, yelahan, "Airport Rd", ARTERIAL, 55),                   # only link -> bridge
        (majestic, mgroad, "KG Rd", ARTERIAL, ART),
        (mgroad, indira, "Old Madras Rd", ARTERIAL, ART),                # parallel pair
        (mgroad, indira, "Indiranagar 100ft Rd", LOCAL, LOC),            # parallel pair
        (indira, krpuram, "Old Madras Rd (E)", ARTERIAL, ART),
        (hebbal, krpuram, "ORR North Expwy", EXPRESSWAY, EXP),
        (krpuram, white, "Whitefield Main Rd", ARTERIAL, ART),           # parallel pair
        (krpuram, white, "ITPL Expwy", EXPRESSWAY, EXP),                 # parallel pair
        (white, marath, "Varthur Rd", ARTERIAL, ART),
        (krpuram, marath, "ORR East", ARTERIAL, ART),
        (marath, hsr, "ORR South Expwy", EXPRESSWAY, EXP),
        (marath, kora, "Koramangala Inner Ring", LOCAL, LOC),
        (indira, kora, "Intermediate Ring Rd", LOCAL, LOC),
        (mgroad, kora, "Hosur Rd (N)", ARTERIAL, ART),
        (kora, hsr, "Sarjapur Rd", LOCAL, LOC),
        (kora, btm, "Koramangala 1st Block Rd", LOCAL, LOC),
        (hsr, silk, "HSR 27th Main", LOCAL, LOC),
        (btm, silk, "BTM Ring Rd", ARTERIAL, ART),
        (silk, ecity, "E-City Elevated Expwy", EXPRESSWAY, EXP),         # parallel pair
        (silk, ecity, "Hosur Rd (S)", LOCAL, 35),                        # parallel pair
        (jaya, btm, "Jayanagar 9th Block Rd", LOCAL, LOC),
        (majestic, jaya, "Lalbagh Rd", ARTERIAL, ART),
        (jaya, banash, "Kanakapura Rd", ARTERIAL, ART),
        (banash, silk, "Banashankari Ring Rd", ARTERIAL, ART),
    ]
    for u, v, name, rtype, speed in roads:
        g.add_road(u, v, name, rtype, speed)

    # ------------------------------------------------------------ inventory
    sys_.unit_weight = {"laptop": 3, "phone": 0.5, "tv": 15, "fridge": 60, "tablet": 1, "headphones": 0.3}
    sys_.add_warehouse("WH-Peenya", peenya, {"laptop": 20, "phone": 40, "tv": 5, "fridge": 4})
    sys_.add_warehouse("WH-Whitefield", white, {"laptop": 10, "phone": 30, "headphones": 50, "tablet": 15})
    sys_.add_warehouse("WH-ElectronicCity", ecity,
                       {"phone": 25, "tv": 2, "fridge": 8, "tablet": 10, "headphones": 20})

    sys_.add_vehicle("Van-01", "van", majestic, 150)
    sys_.add_vehicle("Van-02", "van", kora, 150)
    sys_.add_vehicle("Truck-01", "truck", peenya, 600)
    sys_.add_vehicle("Bike-01", "bike", indira, 15)
    sys_.add_vehicle("Van-03", "van", white, 150)
    sys_.add_vehicle("Truck-02", "truck", silk, 600)

    # =======================================================================
    banner("0. NETWORK  (Temporal Multigraph)")
    print(f"   {g.node_count()} locations, {g.edge_count()} roads (bidirectional)")
    print(f"   parallel roads: Yeshwanthpur-Peenya x{g.multiplicity(yeshwant, peenya)}, "
          f"Hebbal-MG Road x{g.multiplicity(hebbal, mgroad)}, MG Road-Indiranagar x{g.multiplicity(mgroad, indira)},")
    print(f"                   KR Puram-Whitefield x{g.multiplicity(krpuram, white)}, "
          f"Silk Board-Electronic City x{g.multiplicity(silk, ecity)}")
    pi = sys_.product_index
    print(f"   Inverted index: {pi.key_count()} product keys, {pi.bucket_count()} buckets "
          f"(load {pi.load_factor():.2f})")
    for p in ("laptop", "fridge", "tablet"):
        print(f"     '{p}' -> " + " ".join(sys_.warehouses[w].name for w in pi.to_list(p)))

    # =======================================================================
    banner("1. DYNAMIC ROUTE OPTIMISATION  (time-dependent Dijkstra & A*)")
    print("   Same trip Electronic City -> Hebbal at three different times of day.")
    print("   Each parallel road has its own rush-hour profile, so the best ROAD changes:")
    for t in (T(8, 30), T(14), T(23)):
        print(f"\n   Departing {clock(t)} (Dijkstra / Fibonacci heap):")
        print_path(g, dijkstra_fib(g, ecity, hebbal, t))
    dj = dijkstra_fib(g, ecity, yelahan, T(14))
    a_ = astar_fib(g, ecity, yelahan, T(14))
    print(f"\n   Electronic City -> Yelahanka @14:00")
    print(f"     Dijkstra : {dj.minutes:.1f} min, {dj.settled} nodes settled")
    print(f"     A*       : {a_.minutes:.1f} min, {a_.settled} nodes settled  (same answer, smaller search)")

    # =======================================================================
    sys_.now = T(8, 30)
    banner("2. PRIORITY-BASED DELIVERY  (Fibonacci heap)   clock 08:30")
    sys_.place_order("Indiranagar", indira, [("laptop", 2), ("phone", 1)], 2, T(11))
    sys_.place_order("Yelahanka", yelahan, [("fridge", 1)], 3, T(14))
    sys_.place_order("HSR Layout", hsr, [("tv", 1), ("headphones", 2)], 1, T(10, 30))
    sys_.place_order("Jayanagar", jaya, [("phone", 2)], 4, T(16))
    sys_.place_order("KR Puram", krpuram, [("tablet", 2)], 3, T(12))
    sys_.place_order("Banashankari", banash, [("fridge", 2)], 2, T(13))
    sys_.place_order("Koramangala", kora, [("headphones", 1)], 5, T(9, 50))
    sys_.place_order("Malleshwaram", mallesh, [("laptop", 1)], 4, T(17))
    sys_.place_order("Rajajinagar", rajaji, [("tv", 2), ("laptop", 1)], 3, T(13))
    sys_.place_order("Marathahalli", marath, [("phone", 3), ("tablet", 1)], 2, T(11, 30))
    sys_.place_order("MG Road", mgroad, [("tv", 3)], 3, T(15))
    sys_.place_order("BTM Layout", btm, [("tablet", 1), ("phone", 1)], 4, T(15))
    print(f"   {len(sys_.order_queue)} orders inserted into the Fibonacci heap (O(1) each)")
    ok = sys_.cancel_order(7)
    print(f"   Customer cancels order #7 (Malleshwaram) -> heap.remove(handle): {'removed' if ok else 'failed'}")
    print("   Escalation pass (decrease_key for orders near deadline):")
    sys_.escalate()
    print(f"   Queue now holds {len(sys_.order_queue)} orders; head = order #{sys_.order_queue.top().value}")

    # =======================================================================
    banner("3/4/7. WAREHOUSE SELECTION + VEHICLE ASSIGNMENT + CAPACITY CHECKS")
    sys_.dispatch()

    # =======================================================================
    banner("8. MULTI-STOP DELIVERY OPTIMISATION  (NN + 2-opt, deadline aware)")
    sys_.plan_all_routes()
    print()
    sys_.print_fleet()

    # =======================================================================
    banner("5. DYNAMIC RE-ROUTING   clock 09:00")
    sys_.advance_to(T(9))
    # pick a road some vehicle is about to use and close it for 3 hours,
    # and a road another vehicle is about to use and jam it with traffic
    close_edge = jam_edge = -1
    for v in sys_.vehicles:
        if v.status != EN_ROUTE:
            continue
        for i in range(v.progress, len(v.path_edges)):
            if v.path_depart[i] > sys_.now + 5:
                if close_edge < 0:
                    close_edge = v.path_edges[i]
                    break
                if jam_edge < 0 and v.path_edges[i] != close_edge:
                    jam_edge = v.path_edges[i]
                    break
        if close_edge >= 0 and jam_edge >= 0:
            break
    if close_edge >= 0:
        sys_.close_road(close_edge, sys_.now, T(12))
    print()
    if jam_edge >= 0:
        sys_.update_traffic(jam_edge, 3.5)

    # =======================================================================
    banner("6. VEHICLE FAILURE RECOVERY   clock 09:40")
    sys_.advance_to(T(9, 40))
    victim = None
    for v in sys_.vehicles:
        if v.status == EN_ROUTE and v.pending and (victim is None or len(v.pending) > len(victim.pending)):
            victim = v
    if victim:
        sys_.breakdown(victim.id)
        print("\n   Re-dispatching recovered orders:")
        sys_.dispatch()
        sys_.plan_all_routes()
    print()
    sys_.print_fleet()
    vi = sys_.vehicle_index
    print(f"\n   vehicle_index lookups:  status:AVAILABLE={vi.count('status:AVAILABLE')}  "
          f"status:EN_ROUTE={vi.count('status:EN_ROUTE')}  status:BROKEN={vi.count('status:BROKEN')}  "
          f"type:van={vi.count('type:van')}")

    # =======================================================================
    banner("9. LOGISTICS NETWORK ANALYSIS  (BFS, DFS, Tarjan, alternate paths)")
    tA = T(13)          # after the 09:00-12:00 closure has expired
    hops = bfs_reachable(g, peenya, tA)
    reach = sum(1 for h in hops if h >= 0)
    print(f"   BFS from Peenya @13:00: {reach}/{g.node_count()} locations reachable, "
          f"farthest is {max(hops)} hops away")
    _, n_comp = components(g, tA)
    print(f"   DFS connected components @13:00: {n_comp}")
    bridges, cuts = bridges_and_cuts(g, tA)
    print("   Bottleneck roads (bridges): " + " ".join(f"[{g.edges[e].name}]" for e in bridges))
    print("   Critical junctions (articulation points): " + " ".join(f"[{g.nodes[v].name}]" for v in cuts))
    print("   Note: Silk Board-Electronic City has 2 parallel roads, so neither is a bridge -")
    print("         only a MULTIgraph can see that redundancy. Silk Board itself is still a")
    print("         critical junction.")
    print("\n   What-if: both Silk Board-E-City roads closed 15:00-16:00")
    for eid in g.nodes[silk].adj:
        if g.edges[eid].other(silk) == ecity:
            g.add_closure(eid, T(15), T(16))
    _, c1 = components(g, T(15, 30))
    _, c2 = components(g, T(16, 30))
    print(f"     components @15:30 = {c1} (E-City isolated), components @16:30 = {c2} "
          "(road reopened - temporal edges)")

    print("\n   Alternate routes Peenya -> HSR Layout @14:00:")
    for i, p in enumerate(alternate_routes(g, peenya, hsr, T(14), 3), 1):
        print(f"    #{i}")
        print_path(g, p)

    # =======================================================================
    banner("END OF DAY   clock 20:00")
    sys_.advance_to(T(20))
    sys_.print_orders()
    delivered = [o for o in sys_.orders if o.status == DELIVERED]
    on_time = sum(1 for o in delivered if o.delivered_at <= o.deadline)
    km = sum(v.km_driven for v in sys_.vehicles)
    print(f"\n   Delivered {len(delivered)} orders, {on_time} on time; fleet drove {km:.1f} km")
    oi = sys_.order_index
    print(f"   order_index: DELIVERED={oi.count('status:DELIVERED')} CANCELLED={oi.count('status:CANCELLED')} "
          f"BACKORDER={oi.count('status:BACKORDER')}")
    print("\n   (Run  python benchmark.py  for feature 10 - performance analysis.)")


if __name__ == "__main__":
    main()
