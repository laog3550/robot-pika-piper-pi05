#!/usr/bin/env python3
"""Analyse a PI05 arm-probe capture (passive CAN + wrist-camera motion).

Shared by scripts/probe_arm_can_mapping.sh (single guided move) and
scripts/probe_arm_sides.sh (one move per arm).

Method
------
* CAN  : the slave arm of a master/slave pair emits joint feedback on
         0x2A5/0x2A6/0x2A7 as 32-bit BIG-ENDIAN signed millidegrees
         (piper_protocol_base.ConvertBytesToInt defaults to 'big').
         Moving that arm pushes joints outside the envelope they occupied
         while idle. We compare a robust idle envelope against the window.
* Camera: wrist cameras watch a static scene, so a moved arm shows a large
         fraction of samples with high frame-to-frame difference. Judging on
         the fraction (not the peak) rejects auto-exposure spikes.

Both tests are deliberately robust to a stray sample landing in the wrong
window, because the phase boundary is a wall-clock timestamp.
"""

import argparse
import collections
import json
import os
import statistics
import struct
import sys

JOINT_IDS = {0x2A5: ("J1", "J2"), 0x2A6: ("J3", "J4"), 0x2A7: ("J5", "J6")}
SLAVE_FB = set(JOINT_IDS) | {0x2A1, 0x2A2, 0x2A3, 0x2A4, 0x2A8}
MASTER_TX = {0x151, 0x155, 0x156, 0x157, 0x159}
CAN_MOVE_THRESHOLD = 1000      # millidegrees of travel within the window
CAN_NOISE_FLOOR = 300          # millidegrees of idle encoder noise
CAM_ACTIVE_THRESHOLD = 6.0     # frame-difference floor


def pct(vals, p):
    s = sorted(vals)
    if not s:
        return None
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def parse_can(path):
    """-> iface -> cid -> list of (t, data_hex)"""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    if not path or not os.path.exists(path):
        return out
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line.startswith("(") or "#" not in line:
            continue
        try:
            ts = float(line[1:line.index(")")])
            rest = line[line.index(")") + 1:].split()
            iface, frame = rest[0], rest[1]
            cid_s, _, data = frame.partition("#")
            cid = int(cid_s, 16)
        except Exception:
            continue
        out[iface][cid].append((ts, data.upper()))
    return out


def joint_series(parsed):
    """-> iface -> joint name -> list of (t, millidegrees)"""
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for iface, cids in parsed.items():
        for cid, names in JOINT_IDS.items():
            for ts, data in cids.get(cid, ()):
                if len(data) < 16:
                    continue
                try:
                    v = struct.unpack(">ii", bytes.fromhex(data)[:8])
                except Exception:
                    continue
                for j, name in enumerate(names):
                    out[iface][name].append((ts, v[j]))
    return out


def joints_in_window(series, t0, t1):
    return {n: [v for t, v in pts if t0 < t <= t1] for n, pts in series.items()}


def bus_movement(joint_all, base_end, t0, t1):
    """Travel of each bus's joints DURING this window.

    Judged on the WITHIN-WINDOW spread, not on the offset from the idle pose.
    An arm moved in an earlier phase and left parked at a new pose has a large
    offset but zero travel, and must not be reported as moving a second time.
    """
    result = {}
    for iface, series in joint_all.items():
        idle = joints_in_window(series, 0, base_end)
        win = joints_in_window(series, t0, t1)
        score, detail, max_offset = 0.0, [], 0.0
        for name, mv in win.items():
            if not mv:
                continue
            m_lo, m_hi = pct(mv, 0.02), pct(mv, 0.98)
            spread = m_hi - m_lo
            bv = idle.get(name) or []
            idle_spread = (pct(bv, 0.98) - pct(bv, 0.02)) if len(bv) > 4 else 0.0
            noise = max(CAN_NOISE_FLOOR, idle_spread)
            offset = 0.0
            if len(bv) > 4:
                b_lo, b_hi = pct(bv, 0.02), pct(bv, 0.98)
                offset = max(0.0, m_hi - b_hi) + max(0.0, b_lo - m_lo)
            max_offset = max(max_offset, offset)
            if spread > CAN_MOVE_THRESHOLD and spread > 3 * noise:
                score += spread
                detail.append((name, m_lo, m_hi, spread))
        result[iface] = {"score": score, "detail": detail, "offset": max_offset}
    return result


def parse_cam(path):
    out = collections.defaultdict(list)
    if not path or not os.path.exists(path):
        return out
    for line in open(path, errors="replace"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        out[r["cam"]].append((r["t"], r["energy"]))
    return out


def cam_movement(cam_all, base_end, t0, t1):
    result = {}
    for cam, pts in cam_all.items():
        idle = [e for t, e in pts if t <= base_end]
        win = [e for t, e in pts if t0 < t <= t1]
        if not idle or not win:
            result[cam] = {"moved": False, "reason": "insufficient samples",
                           "n_idle": len(idle), "n_win": len(win)}
            continue
        thr = max(CAM_ACTIVE_THRESHOLD, pct(idle, 0.95) * 1.5)
        bf = sum(1 for e in idle if e > thr) / len(idle)
        wf = sum(1 for e in win if e > thr) / len(win)
        result[cam] = {
            "moved": wf > 0.25 and wf > bf * 3,
            "idle_mean": statistics.mean(idle), "win_mean": statistics.mean(win),
            "peak": max(win), "thr": thr, "idle_frac": bf, "win_frac": wf,
        }
    return result


def role_of(cids):
    has_master = any(c in MASTER_TX for c in cids)
    has_slave = any(c in SLAVE_FB for c in cids)
    if has_master and has_slave:
        return "MASTER + SLAVE pair"
    if has_master:
        return "MASTER only (teaching input; no slave feedback)"
    if has_slave:
        return "SLAVE only (motion output; no master control frames)"
    return "unrecognised traffic" if cids else "no traffic"


def master_tx_counts(parsed, t0, t1):
    """Control frames 0x151/0x155/0x156/0x157/0x159 seen per interface.

    A master arm in teaching-input (linkage) mode transmits these and nothing
    else, so their appearance identifies which bus carries a master arm.
    """
    out = {}
    for iface, cids in parsed.items():
        n = 0
        for cid in MASTER_TX:
            n += sum(1 for ts, _ in cids.get(cid, ()) if t0 < ts <= t1)
        out[iface] = n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--can-log")
    ap.add_argument("--cam-log")
    ap.add_argument("--baseline-end", type=float, required=True)
    ap.add_argument("--window", action="append", default=[],
                    help="NAME:START:END (repeatable)")
    ap.add_argument("--json")
    args = ap.parse_args()

    windows = []
    for w in args.window:
        name, a, b = w.split(":")
        windows.append((name, float(a), float(b)))

    parsed = parse_can(args.can_log)
    joint_all = joint_series(parsed)
    cam_all = parse_cam(args.cam_log)

    all_t = [t for cids in parsed.values() for pts in cids.values() for t, _ in pts]
    report = {"interfaces": {}, "windows": {}, "cameras": {}}

    print()
    print("=" * 68)
    print(" PASSIVE CAN INVENTORY")
    print("=" * 68)
    if not parsed or not all_t:
        print("  No CAN traffic captured on any interface.")
        print("  -> arms unpowered, CAN cable unplugged, or wrong bitrate.")
    else:
        print(f"  capture span: {min(all_t):.3f} .. {max(all_t):.3f} "
              f"({max(all_t) - min(all_t):.1f}s)")
        for iface in sorted(parsed):
            cids = sorted(parsed[iface])
            n = sum(len(v) for v in parsed[iface].values())
            static = sum(1 for c in cids
                         if len({d for _, d in parsed[iface][c]}) == 1)
            info = {"frames": n, "ids": [hex(c) for c in cids],
                    "role": role_of(cids), "static_ids": static}
            report["interfaces"][iface] = info
            print(f"  {iface}: {info['role']}")
            print(f"      frames={n}  ids={' '.join(info['ids']) or '<none>'}")
            print(f"      ids that never changed payload while idle: {static}/{len(cids)}"
                  if cids else "")

    for name, t0, t1 in windows:
        print()
        print("=" * 68)
        print(f" WINDOW {name}   ({t0:.3f} .. {t1:.3f}, {t1 - t0:.1f}s)")
        print("=" * 68)
        bm = bus_movement(joint_all, args.baseline_end, t0, t1)
        cm = cam_movement(cam_all, args.baseline_end, t0, t1)
        mtx = master_tx_counts(parsed, t0, t1)
        mtx_idle = master_tx_counts(parsed, 0, args.baseline_end)
        moved_buses, moved_cams, master_buses = [], [], []
        for iface in sorted(set(bm) | set(mtx)):
            r = bm.get(iface, {"score": 0.0, "detail": []})
            if r["score"] > 0:
                moved_buses.append(iface)
            if mtx.get(iface, 0) > 0:
                master_buses.append(iface)
            print(f"  {iface}: travel score {r['score']:.0f} (0.001 deg)"
                  f"{'   <== MOVED' if r['score'] > 0 else ''}")
            print(f"      master control frames (0x151/155/156/157/159): "
                  f"idle={mtx_idle.get(iface, 0)} window={mtx.get(iface, 0)}"
                  f"{'   <== MASTER ACTIVE' if mtx.get(iface, 0) > mtx_idle.get(iface, 0) else ''}")
            for nm, m_lo, m_hi, spread in r["detail"]:
                print(f"        {nm}: moved {m_lo / 1000:.2f}..{m_hi / 1000:.2f} deg "
                      f"(travel {spread / 1000:.2f} deg)")
            if r["score"] == 0 and r.get("offset", 0) > CAN_MOVE_THRESHOLD:
                print(f"      note: not moving this window, but parked "
                      f"{r['offset'] / 1000:.2f} deg away from its idle pose")
        for cam in sorted(cm):
            r = cm[cam]
            if r.get("moved"):
                moved_cams.append(cam)
            if "reason" in r:
                print(f"  {cam}: {r['reason']}")
            else:
                print(f"  {cam}: idle_mean={r['idle_mean']:.2f} "
                      f"moved_mean={r['win_mean']:.2f} peak={r['peak']:.2f} "
                      f"active_frac {r['idle_frac']:.2f}->{r['win_frac']:.2f}"
                      f"{'   <== MOVED' if r['moved'] else ''}")
        report["windows"][name] = {"buses_moved": moved_buses,
                                   "cameras_moved": moved_cams,
                                   "master_active": master_buses}
        print()
        print(f"  ==> in this window, bus(es) whose ARM moved : {moved_buses or 'NONE'}")
        print(f"  ==> in this window, bus(es) with a MASTER   : {master_buses or 'NONE'}")
        print(f"  ==> in this window, camera(s) that moved    : {moved_cams or 'NONE'}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nJSON summary written to {args.json}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
