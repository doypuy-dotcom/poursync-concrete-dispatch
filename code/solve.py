"""AI Concrete — the ONE command every team must keep working (the organisers run it on the hidden Day 5).

    python solve.py <day_dir> <out_dir>
    python solve.py ../data/day1_weekday ../out/day1

Reads one day folder (and ../common), writes <out_dir>/plan.csv, order_changes.csv, production_plan.csv.
Rules for the hidden day: same command, no internet, no manual edits, finish within 5 minutes.
Replace plan_day() with your own solver (any language is fine as long as this command produces the 3 files).
"""
import os
import sys

from aiconcrete import kpis, load_day, read_plan, simulate, write_csv
from baseline_greedy import plan_day


def main():
    day_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    day = load_day(day_dir)

    # ---------- ลองหลายค่าของ n_plants แล้วให้ตัวจำลองตัดสินว่าค่าไหนดีที่สุด ----------
    # n_plants = จำนวนโรงงานที่ใกล้หน่วยงานที่สุด ที่ยอมเอามาพิจารณาต่อหนึ่งเที่ยว
    # ยิ่งมาก ยิ่งมีทางเลือกรถ/ไลน์มากขึ้น แต่ก็เสี่ยงไปหยิบโรงงานไกลจนเวลาเดินทางบานปลาย
    # วันไหนเหมาะกับค่าไหน เดาล่วงหน้าไม่ได้ (วันลับยิ่งเดาไม่ได้) จึงลองทุกค่าแล้ววัดผลจริง
    # boost = ขอเพิ่มไลน์ผลิตหรือไม่ (มีค่าใช้จ่ายรายชั่วโมง จึงต้องลองทั้งสองแบบ)
    options = [(2, False), (3, False), (4, False), (2, True), (3, True), (4, True)]
    tmp_path = os.path.join(out_dir, "_try_plan.csv")
    best = None
    best_score = None
    for n, boost in options:
        # โหลดข้อมูลของวันใหม่ทุกรอบ เพื่อให้แต่ละรอบเริ่มจากสภาพเดิมเสมอ
        plan, changes, production = plan_day(load_day(day_dir), n, boost)

        # เขียนแผนลงไฟล์ชั่วคราวก่อน แล้วอ่านกลับด้วย read_plan
        # เพื่อให้ผ่านขั้นตอนเดียวกับที่ผู้จัดใช้ตรวจ (กันพลาดเรื่องรูปแบบไฟล์)
        write_csv(tmp_path, plan, ["stream_id", "seq", "plant_id", "truck_id", "load_start"])

        # รันตัวจำลองของกติกาจริง แล้วคิดคะแนน
        sim, errors = simulate(load_day(day_dir), read_plan(tmp_path),
                               production or None, changes or None)
        res = kpis(load_day(day_dir), sim, errors)

        # เรียงความสำคัญเหมือนกติกาจัดอันดับ:
        #   1) SLA ผ่านไหม  2) Contribution
        # ไม่เอา sla_checks_passed มาคิด เพราะอันดับจริงไม่ได้ดูว่าผ่านกี่เกณฑ์
        # ดูแค่ว่า "ผ่านทั้งวันหรือไม่" ถ้าผ่านเท่ากันค่อยเอากำไรสูงกว่า
        score = (res["sla_pass"], res["contribution_baht"])
        print(f"try n_plants = {n}, boost = {boost} -> {score}")

        # ดีกว่าของเดิมก็เก็บไว้
        if best_score is None or score > best_score:
            best_score = score
            best = (plan, changes, production)

        # ลบไฟล์ชั่วคราว ไม่ให้ค้างอยู่ในโฟลเดอร์ผลลัพธ์
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # ใช้แบบที่ดีที่สุดเขียนเป็นไฟล์ผลลัพธ์จริง
    plan, changes, production = best
    write_csv(os.path.join(out_dir, "plan.csv"), plan, ["stream_id", "seq", "plant_id", "truck_id", "load_start"])
    write_csv(os.path.join(out_dir, "order_changes.csv"), changes, ["order_id", "new_first_arrival", "reason"])
    write_csv(os.path.join(out_dir, "production_plan.csv"), production, ["plant_id", "extra_lines", "from", "to"])
    print(f"Day {day.info.get('day')} {day.info.get('event')}: {len(plan)} loads -> {out_dir}")


if __name__ == "__main__":
    main()
