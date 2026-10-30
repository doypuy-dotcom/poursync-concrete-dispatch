# Notes

## What we found in the data
1. **Plant capacity in the system was wrong.** Production notes said P05 had one line under repair (real: 2 lines, system: 3) and P07 had a new line (real: 3, system: 2). Plant load history agreed (max 10 vs 12 loads/hour). The plan was re-checked with the real capacity and SLA results did not change.
2. **Trucks, not plant lines, were the bottleneck.** No load waited for a production line, and adding every optional line kept SLA the same while costing 65,900 THB, so the final plan adds no lines.
3. **Some jobs cannot be fixed by dispatching alone.** A school-zone site booked at 07:30 inside a 06:30–08:30 truck ban, and a 22-load festival pour running into the evening road closure. Both customers allow time shifts, so the fix is a business decision: ask them to move.

## What worked
| Idea | Effect |
|---|---|
| Correct load start by the simulated arrival error | Main fix for late first trucks on traffic days |
| Scan load start −60…+9 min | Fixed cases where leaving earlier lands in a different traffic period |
| Customer time shifts for no-entry windows | Fixed the Day 2 school-zone orders and was needed to pass Day 3 (road closure) |
| Portfolio of 6 plans scored by the simulator | Day 3 needs the 3 nearest plants, but using 3 on every day breaks Day 4; choosing per day passes both |

## What did not work
- More correction rounds (5 instead of 2): no extra SLA checks.
- Allowing all 8 plants for every load: longer trips, no gain.
- Simply sorting loads by customer grade: did not fix continuity.
- Using 3 nearest plants for every day: passed Day 3 but broke Day 4, which is why the portfolio approach was added.
- Bug found on the way: correcting a load start could make a load leave before the previous load of the same pour → simulator hard error. Fixed by never starting earlier than the previous load.

## Why Days 1–2 still fail
On-time checks pass on every day; **all failed checks are continuity** (gaps between trucks). On Day 1, large G1–G2 pours start at the same time (09:45–10:30), so the trucks for loads 2, 3, 4… of each pour are not free in time. The current plan sets each load's target from the *planned* first arrival, not from when the previous truck actually finishes pouring.

## Next steps
1. Set each load's target from the previous load's actual pour end, not a fixed schedule.
2. Repair loop: after a full plan, remove the loads of broken pours and re-insert them, keep the change only if SLA improves.
3. Let G1–G2 pours reserve trucks first; reposition idle trucks earlier.
4. Fix the edge case where no feasible option exists for a load (`best is None`).
