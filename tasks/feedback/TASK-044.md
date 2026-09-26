Round 1 (DeepSeek): one wrong test expectation (a 100 -> 110 round trip is a win). On real
data two defects, fixed by Claude: orders were joined on signal_id only, and a signal id is
shared across SIMULATION / SHADOW / LIVE, so "delay" came from another mode's earlier order
(~700 s; true ~4 s); and the expected price took any earlier mark (another mode, or
yesterday's), which invented +263 bps on a buy. Now same mode and within 15 minutes, else
None ("not recorded"). The engine does not store its decision-time quote — proposed as a
separate change on a branch.
