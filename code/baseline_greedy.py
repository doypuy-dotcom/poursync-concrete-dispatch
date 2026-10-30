"""AI Concrete — Level 1 starting point. Improve it!

Idea: take every load in order of the time the customer wants it, try the 2 nearest plants that can make the
product and every truck of the right size, keep the option that arrives closest to the target time. Uses the
official simulator (aiconcrete.Sim) so what you see is what the judges compute — with the data you give it.

What it does NOT do yet (your job): true plant capacity, traffic events, school / closure windows, customer
behaviour, morning repositioning, production boost, asking customers to move (order_changes.csv), cost, CO2 ...
"""
import math

from aiconcrete import Sim, m2t


def latest_plant_close(day):
    """เวลาปิดของโรงงานที่ปิดช้าที่สุดในวันนั้น (นาทีนับจากเที่ยงคืน)

    ใช้เป็นเพดานความปลอดภัย: ถ้าช่วงห้ามเข้าไปจบหลังโรงงานปิดหมดแล้ว
    การเลื่อนเป้าหมายไปรอก็ไม่มีประโยชน์ เพราะไม่มีไลน์ผลิตให้โหลดอีกแล้ว
    """
    close = 0
    for pid in day.plants:
        p = day.plants[pid]
        if p["close_m"] > close:
            close = p["close_m"]
    return close


def move_out_of_no_entry(day, site_id, t, close_limit):
    """เลื่อนเวลาเป้าหมาย t ออกจากช่วงที่ห้ามรถบรรทุกเข้าหน่วยงาน

    ช่วงห้ามเข้าใน site["no_entry"] มาจากสองทาง และซ้อนกันได้:
      1. ของหน่วยงานเอง (คอลัมน์ no_entry_windows เช่น เขตชั้นในห้ามรถบรรทุก)
      2. เหตุการณ์ของวันนั้นที่ปิดถนน (traffic_events ที่ no_entry_for_sites = 1)
    เช่น ช่วง 16:00-19:00 กับ 17:00-22:00 ซ้อนกัน เลื่อนไป 19:00 แล้วยังอยู่ในอีกช่วง
    จึงต้องวนตรวจซ้ำจนกว่าจะพ้นทุกช่วง

    ถ้าเลื่อนแล้วเลยเวลาโรงงานปิด ให้คืนค่าเดิม (ไม่เลื่อน) เพราะเลื่อนไปก็โหลดไม่ได้
    """
    site = day.sites[site_id]
    new_t = t
    for rob in range(10):
        moved = False
        for a, b in site["no_entry"]:
            if a <= new_t < b:
                new_t = b
                moved = True
        if not moved:
            break
    # เลื่อนไปไกลเกินเวลาที่โรงงานยังเปิดอยู่ -> ไม่คุ้ม ใช้เวลาเดิมดีกว่า
    if new_t >= close_limit:
        return t
    return new_t


def plan_day(day, n_plants=2, boost=False):
    """Return (plan_rows, order_changes_rows, production_rows) for one day."""
    # ---------- ขอลูกค้าเลื่อนเวลานัด ให้ "ช่วงงานทั้งงาน" พ้นช่วงห้ามรถบรรทุกเข้าหน่วยงาน ----------
    # เดิมดูแค่เวลานัดของเที่ยวแรก แต่งานหนึ่งกินเวลาหลายชั่วโมง
    # ถ้าเริ่มทันแต่ไปจบกลางช่วงห้ามเข้า เที่ยวท้าย ๆ ก็เข้าไม่ได้ ต้องจอดแช่จนคอนกรีตหมดอายุ
    # ใหม่: คิดความยาวงานทั้งงาน (span) แล้วค่อย ๆ ขยับเวลาเริ่มทีละ 5 นาที
    #       ไปในทิศที่ลูกค้ายอม จนกว่าช่วงงานทั้งช่วงจะไม่ทับช่วงห้ามเข้าเลย
    changes = []
    for oid in day.orders:
        sids = day.orders[oid]
        s0 = day.streams[sids[0]]
        cust = day.customers[s0["customer_id"]]
        t = s0["first_arrival"]

        # span = ความยาวงาน นับจากสายเทที่กินเวลานานที่สุดใน order นี้
        # (หลายสายเทเทพร้อมกัน เช่น ใช้ปั๊ม 2 ตัว จึงเอาตัวที่ยาวสุด ไม่ใช่เอามาบวกกัน)
        span = 0
        for sid in sids:
            s = day.streams[sid]
            one = s["loads"] * s["interval_min"]
            if one > span:
                span = one

        bans = day.sites[s0["site_id"]]["no_entry"]

        # ลูกค้ายอมเลื่อนไปทางไหน ถ้าไม่ยอมเลยก็ข้าม order นี้ไป
        if cust["flex_type"] == "later_ok":
            step = 5            # ขยับไปข้างหลังทีละ 5 นาที
        elif cust["flex_type"] == "earlier_ok":
            step = -5           # ขยับมาข้างหน้าทีละ 5 นาที
        else:
            continue

        # ลองเลื่อน 0, step, 2*step, ... เท่าที่ลูกค้ายอม (flex_max_shift_min)
        found = None
        shift = 0
        while abs(shift) <= cust["flex_max_shift_min"]:
            a0 = t + shift              # ช่วงงานเริ่ม
            b0 = a0 + span              # ช่วงงานจบ
            clash = False
            for a, b in bans:
                # สองช่วงทับกันเมื่อ จุดเริ่มของช่วงแรกน้อยกว่าจุดจบของช่วงหลัง และสลับกันด้วย
                if a0 < b and a < b0:
                    clash = True
            if not clash:
                found = shift
                break
            shift = shift + step

        # เจอเวลาที่พ้นช่วงห้ามเข้า และต้องขยับจริง (ถ้า shift = 0 ก็ไม่ต้องขอลูกค้า)
        if found is not None and found != 0:
            changes.append(dict(order_id=oid, new_first_arrival=m2t(t + found),
                                reason="avoid site no-entry window"))
    # ส่ง changes เข้าตัวจำลอง เพื่อให้ sim.first_arrival เป็นเวลานัดใหม่หลังเลื่อน
    # ---------- ขอเพิ่มไลน์ผลิต (production_plan.csv) ----------
    # บางโรงงานเช่าเครื่องผสมเพิ่ม/เปิดไลน์ OT ได้ ดูจาก boost_max_lines และ boost_from/boost_to
    # มีค่าใช้จ่ายต่อชั่วโมง (boost_cost_per_hour) จึงไม่ใช่ว่าขอแล้วดีขึ้นเสมอ
    # เราไม่ตัดสินเองว่าควรขอหรือไม่ แต่ให้ solve.py ลองทั้งสองแบบแล้ววัดผลจริง
    # หมายเหตุ: ใช้ {"from": ...} ไม่ใช่ dict(from=...) เพราะ from เป็นคำสงวนของ Python
    production = []
    if boost:
        for pid in day.plants:
            p = day.plants[pid]
            if p["boost_max_lines"] > 0 and p["boost_from"]:
                production.append({"plant_id": pid,
                                   "extra_lines": p["boost_max_lines"],
                                   "from": p["boost_from"],
                                   "to": p["boost_to"]})

    sim = Sim(day, production, changes)
    close_limit = latest_plant_close(day)
    loads = []
    for sid, s in day.streams.items():
        # เดิม: เป้าหมายของเที่ยวที่ k = เวลาที่ลูกค้าขอ + (k-1) x ระยะห่างที่ประกาศไว้
        # ปัญหา: ถ้าเวลานั้นตกอยู่ในช่วงห้ามรถบรรทุกเข้าหน่วยงาน รถจะเข้าไม่ได้
        #        ต้องไปจอดแช่อยู่หน้าเขตห้ามเข้าจนกว่าช่วงนั้นจะหมด
        #        ระหว่างนั้นอายุคอนกรีตเดินตลอด พอถึงคิวเทก็เลยอายุ -> ทิ้งทั้งคัน
        # ใหม่: ถ้าเป้าหมายตกในช่วงห้ามเข้า ให้เลื่อนไปเป็นตอนที่ช่วงนั้นหมด
        #       แล้วเที่ยวถัด ๆ ไปนับระยะห่างต่อจากเวลาใหม่ (ไม่ใช่ทุกเที่ยวกองที่เวลาเดียวกัน)
        # ใช้ sim.first_arrival[sid] ไม่ใช่ s["first_arrival"]
        # เพราะถ้า order นี้ถูกขอเลื่อนไปแล้ว เวลานัดจริงคือเวลาใหม่
        t = sim.first_arrival[sid]
        for k in range(1, s["loads"] + 1):
            if k > 1:
                t = t + s["interval_min"]
            t = move_out_of_no_entry(day, s["site_id"], t, close_limit)
            loads.append((t, sid, k))
    loads.sort()
    rows, last = [], {}
    for target, sid, k in loads:
        s = day.streams[sid]
        ok = [p for p in day.plants if (p, s["product_id"]) in day.plant_product]
        plants = sorted(ok, key=lambda p: day.travel[(p, s["site_id"])]["km"])[:n_plants]
        best = None
        for pid in plants:
            p = day.plants[pid]
            planned = max(last.get(sid, 0),
                          target - day.travel[(pid, s["site_id"])]["normal"] - p["mix_load_min"] - p["qc_min"])
            for tid, t in day.trucks.items():
                if t["size"] != s["truck_size"] or (t["allowed"] is not None and pid not in t["allowed"]):
                    continue
                r = sim.preview(sid, k, pid, tid, round(planned))

                # ---------- ปรับเวลาโหลดให้ไปถึงใกล้เวลาที่ลูกค้าขอมากขึ้น (วนไม่เกิน 2 รอบ) ----------
                # ทำไมต้องปรับ: สูตร planned ข้างบนใช้เวลาเดินทางแบบ "normal" เสมอ
                # แต่เวลาจริงขึ้นกับช่วงที่ออกรถ (offpeak/normal/peak/holiday) และเหตุการณ์ของวันนั้น
                # ถ้าวันนั้นรถติด เวลาจริงจะนานกว่าที่คิด รถจึงไปถึงสาย
                # วิธีแก้: ดูว่าพลาดไปกี่นาที แล้วเลื่อนเวลาโหลดสวนทางกับความคลาดเคลื่อนนั้น
                for rob in range(2):
                    # ถ้าเที่ยวนี้มีปัญหาอยู่แล้ว (รถผิดขนาด / โรงงานผลิตไม่ได้ / ไม่มีไลน์ว่าง)
                    # ปรับเวลาไปก็ไม่ช่วย ให้หยุด
                    if r["problems"]:
                        break

                    # err เป็นบวก = ไปถึงสายกว่าเป้าหมาย
                    # err เป็นลบ  = ไปถึงเร็วกว่าเป้าหมาย
                    err = r["arrive"] - target

                    # ถ้าคลาดเคลื่อนไม่ถึง 1 นาที ถือว่าดีพอแล้ว ไม่ต้องปรับต่อ
                    if abs(err) < 1:
                        break

                    # สายไป -> โหลดให้เร็วขึ้น | เร็วไป -> โหลดให้ช้าลง
                    new_start = r["load_start"] - err

                    # ห้ามโหลดก่อนเที่ยวก่อนหน้าของสายเทเดียวกัน (เที่ยวต้องเรียงตาม seq)
                    if new_start < last.get(sid, 0):
                        new_start = last.get(sid, 0)

                    # ถ้าเวลาใหม่กับเวลาเดิมเท่ากันอยู่แล้ว ปรับต่อก็ไม่มีอะไรเปลี่ยน
                    if round(new_start) == round(r["load_start"]):
                        break

                    # ลองดูว่าถ้าใช้เวลาโหลดใหม่ ผลจะเป็นอย่างไร (preview ไม่ผูกมัดอะไร)
                    r2 = sim.preview(sid, k, pid, tid, round(new_start))

                    # เวลาใหม่ทำให้เกิดปัญหา -> ทิ้งผลใหม่ ใช้ผลเดิมต่อ
                    if r2["problems"]:
                        break

                    # เวลาใหม่ไม่ได้เข้าใกล้เป้าหมายมากขึ้น -> ทิ้งผลใหม่ ใช้ผลเดิมต่อ
                    if abs(r2["arrive"] - target) >= abs(err):
                        break

                    # ถึงตรงนี้แปลว่าดีขึ้นจริง รับผลใหม่ แล้ววนไปปรับอีกรอบ
                    r = r2
                # ------------------------------------------------------------------------------

                # ---------- ถ้ายังพลาดเป้าหมายอยู่ ให้กวาดหาเวลาโหลดที่ดีกว่า ----------
                # ลูปข้างบนขยับแค่ 2 รอบ ซึ่งบางทีไม่พอ เพราะเลื่อนเวลาโหลดแล้ว
                # ช่วงจราจรก็เปลี่ยนตาม (เช่น ข้ามจาก peak ไป normal) เวลาเดินทางจึงกระโดด
                # วิธีที่แน่กว่า: ลองเวลาโหลดหลาย ๆ ค่ารอบ ๆ ค่าที่ได้ แล้วเก็บค่าที่ดีที่สุด
                if not r["problems"] and abs(r["arrive"] - target) > 2:
                    base = round(r["load_start"])
                    # กวาดจาก 60 นาทีก่อน ถึง 10 นาทีหลัง ทีละ 3 นาที
                    for ls in range(base - 60, base + 11, 3):
                        # ห้ามโหลดก่อนเที่ยวก่อนหน้าของสายเทเดียวกัน
                        if ls < last.get(sid, 0):
                            continue
                        r3 = sim.preview(sid, k, pid, tid, ls)
                        if r3["problems"]:
                            continue
                        # เข้าใกล้เวลาเป้าหมายกว่าเดิมไหม
                        if abs(r3["arrive"] - target) < abs(r["arrive"] - target):
                            r = r3
                # ------------------------------------------------------------------------------

                if r["problems"]:
                    continue
                score = abs(r["arrive"] - target)
                if best is None or score < best[0]:
                    best = (score, r)
        r = best[1]
        if r["load_start"] != int(r["load_start"]):   # CSV holds whole minutes
            r = sim.preview(sid, k, r["plant_id"], r["truck_id"], math.ceil(r["load_start"]))
        r["planned"] = r["load_start"]
        sim.commit(r)
        last[sid] = r["load_start"]
        rows.append(dict(stream_id=sid, seq=k, plant_id=r["plant_id"], truck_id=r["truck_id"],
                         load_start=m2t(r["load_start"])))
    rows.sort(key=lambda r: (r["load_start"], r["stream_id"], r["seq"]))
    return rows, changes, production
