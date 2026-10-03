"""v0.8.5.4 real-world memory validation: 4 x 15-track SETs through the packaged UI, then reopen.

Drives the packaged exe with MWS_TEST_QUEUE_PLAN (real add-folder -> analyze -> add SET -> start
queue flow) in an isolated LOCALAPPDATA with a cold analysis cache. User audio is only read.

    .venv312\\Scripts\\python.exe tools\\validate_v0854_memory.py --audio-root "D:\\suno\\업로드"
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, re, subprocess, threading, time
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parents[1]
SETS = [("ja02", "templates/00_v0850_tokyo_silk_wave.json"), ("ja03", "templates/00_v0831_her_silk_ribbon.json"),
        ("ja05", "templates/00_v0831_her_lavender_line.json"), ("ja06", "templates/00_v0850_tokyo_two_hearts.json")]
REOPEN_SET = ("ja07", "templates/00_v0850_tokyo_midnight_pulse.json")


class Sampler(threading.Thread):
    """1 s psutil sampler for the app process and its FFmpeg children."""
    def __init__(self, pid):
        super().__init__(daemon=True); self.pid = pid; self.rows = []; self.stop = False
    def run(self):
        try: app = psutil.Process(self.pid)
        except psutil.Error: return
        while not self.stop:
            try:
                info = app.memory_info(); kids = [c for c in app.children(recursive=True) if "ffmpeg" in c.name().lower()]
                self.rows.append({"t": dt.datetime.now(), "rss": info.rss / 2**20, "private": info.private / 2**20, "handles": app.num_handles(), "threads": app.num_threads(), "ffmpeg": len(kids), "available": psutil.virtual_memory().available / 2**20})
            except psutil.Error: break
            time.sleep(1)


def run_app(exe, local, plan, out_dir, label, timeout_s):
    env = dict(os.environ, LOCALAPPDATA=str(local), MWS_TEST_QUEUE_PLAN=str(plan), MWS_TEST_NONINTERACTIVE="1")
    started = dt.datetime.now(); proc = subprocess.Popen([str(exe)], env=env)
    watch = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools/memory_watch.ps1"), "-Output", str(out_dir / f"memory_watch_{label}.csv"), "-AppPid", str(proc.pid), "-IntervalSeconds", "5"])
    sampler = Sampler(proc.pid); sampler.start()
    try: code = proc.wait(timeout_s)
    except subprocess.TimeoutExpired: proc.kill(); code = "timeout"
    sampler.stop = True; sampler.join(5); watch.wait(30)
    return {"label": label, "exit_code": code, "started": started, "ended": dt.datetime.now(), "pid": proc.pid, "rows": sampler.rows}


def memory_lines(log_path, since):
    pattern = re.compile(r"^(\S+ \S+),\d+ INFO MEMORY stage=(\S+) (.*)$"); result = []
    for line in Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if not match: continue
        stamp = dt.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        if stamp < since.replace(microsecond=0): continue
        fields = dict(item.split("=", 1) for item in match.group(3).split() if "=" in item)
        result.append({"t": stamp, "stage": match.group(2), **fields})
    return result


def set_table(run, lines):
    starts = [l for l in lines if l["stage"] == "set_start"]; ends = [l for l in lines if l["stage"] == "set_end"]; table = []
    for index, (start, end) in enumerate(zip(starts, ends), 1):
        window = [r for r in run["rows"] if start["t"] <= r["t"] <= end["t"] + dt.timedelta(seconds=1)]
        table.append({"set": index, "start_rss": float(start["rss_mb"]), "start_private": float(start["private_mb"]), "start_handles": int(start["handles"]), "start_threads": int(start["threads"]),
                      "peak_rss": max([r["rss"] for r in window] or [0]),
                      "peak_private": max([r["private"] for r in window] or [0]), "max_handles": max([r["handles"] for r in window] or [0]), "max_threads": max([r["threads"] for r in window] or [0]),
                      "end_rss": float(end["rss_mb"]), "end_private": float(end["private_mb"]), "end_handles": int(end["handles"]), "end_threads": int(end["threads"]),
                      "seconds": (end["t"] - start["t"]).total_seconds(), "ok": end.get("ok")})
    return table


def windows_events(since):
    script = ("$s=[datetime]'%s';Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=$s} -ErrorAction SilentlyContinue | "
              "Where-Object {$_.ProviderName -in 'Application Error','Windows Error Reporting','Application Hang','Microsoft-Windows-Resource-Exhaustion-Detector'} | "
              "ForEach-Object {'{0}|{1}|{2}|{3}' -f $_.TimeCreated.ToString('s'),$_.ProviderName,$_.Id,(($_.Message -replace '\\s+',' ').Substring(0,[Math]::Min(300,$_.Message.Length)))};"
              "Get-WinEvent -FilterHashtable @{LogName='System';StartTime=$s;ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector'} -ErrorAction SilentlyContinue | ForEach-Object {'{0}|{1}|{2}|resource exhaustion' -f $_.TimeCreated.ToString('s'),$_.ProviderName,$_.Id}") % since.strftime("%Y-%m-%d %H:%M:%S")
    output = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return [line for line in output.splitlines() if line.strip()]


def probe_duration(ffprobe, path):
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(result.stdout.strip() or 0)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--audio-root", default="D:/suno/업로드"); parser.add_argument("--work", default=str(ROOT / "_v0854_real" / "run")); parser.add_argument("--exe", default=str(ROOT / "dist/MusicWaveStudio_v0.8.5.4/MusicWaveStudio_v0.8.5.4.exe")); parser.add_argument("--limit", type=int, default=15); parser.add_argument("--reopen-delay-ms", type=int, default=60000)
    args = parser.parse_args(); work = Path(args.work); work.mkdir(parents=True, exist_ok=True); local = work / "local"; exe = Path(args.exe)
    audio = Path(args.audio_root); since = dt.datetime.now()
    plan1 = {"sets": [{"folder": str(audio / folder), "template": str(ROOT / template), "limit": args.limit, "output": str(work / "out" / f"set{i+1}_{folder}")} for i, (folder, template) in enumerate(SETS)], "idle_ms": 30000, "report": str(work / "plan1.report.json")}
    plan2 = {"sets": [{"folder": str(audio / REOPEN_SET[0]), "template": str(ROOT / REOPEN_SET[1]), "limit": args.limit, "output": str(work / "out" / f"set5_{REOPEN_SET[0]}")}], "start_delay_ms": args.reopen_delay_ms, "idle_ms": 10000, "report": str(work / "plan2.report.json")}
    # The UI falls back to <audio folder>/wave when the output folder does not exist; never write next to user audio.
    for item in plan1["sets"] + plan2["sets"]: Path(item["output"]).mkdir(parents=True, exist_ok=True)
    (work / "plan1.json").write_text(json.dumps(plan1, ensure_ascii=False, indent=2), encoding="utf-8"); (work / "plan2.json").write_text(json.dumps(plan2, ensure_ascii=False, indent=2), encoding="utf-8")
    run1 = run_app(exe, local, work / "plan1.json", work, "4set", 4 * 3600)
    time.sleep(10)
    leftovers = [p.info for p in psutil.process_iter(["pid", "name", "ppid"]) if (p.info["name"] or "").lower().startswith("ffmpeg") and p.info["ppid"] == run1["pid"]]
    app_alive = psutil.pid_exists(run1["pid"])
    run2 = run_app(exe, local, work / "plan2.json", work, "reopen", 2 * 3600)
    log = local / "MusicWaveStudio" / "logs" / "music_wave_studio.log"
    lines1 = [l for l in memory_lines(log, run1["started"]) if l["t"] <= run1["ended"]]; lines2 = memory_lines(log, run2["started"])
    table1 = set_table(run1, lines1); table2 = set_table(run2, lines2)
    ffprobe = str(exe.parent / "_internal" / "ffprobe.exe"); outputs = []
    for item in plan1["sets"] + plan2["sets"]:
        for video in Path(item["output"]).glob("*_WAVE.*"):
            timeline = json.loads(next(Path(item["output"]).glob("*_timeline.json")).read_text(encoding="utf-8"))
            outputs.append({"video": str(video), "duration": probe_duration(ffprobe, video), "timeline_duration": timeline["total_duration"], "tracks": len(timeline["tracks"])})
    log_text = log.read_text(encoding="utf-8", errors="replace"); since_text = run1["started"].strftime("%Y-%m-%d %H:%M")
    criticals = [line for line in log_text.splitlines() if (" CRITICAL " in line or "Traceback" in line) and line[:16] >= since_text]
    rows = run1["rows"] + run2["rows"]
    report = {"since": since.isoformat(), "run1_exit": run1["exit_code"], "run2_exit": run2["exit_code"], "run1_minutes": (run1["ended"] - run1["started"]).total_seconds() / 60, "run2_minutes": (run2["ended"] - run2["started"]).total_seconds() / 60,
              "plan1_report": json.loads(Path(plan1["report"]).read_text(encoding="utf-8")), "plan2_report": json.loads(Path(plan2["report"]).read_text(encoding="utf-8")),
              "sets": table1, "reopen_sets": table2, "max_rss": max(r["rss"] for r in rows), "max_private": max(r["private"] for r in rows), "max_handles": max(r["handles"] for r in rows), "max_threads": max(r["threads"] for r in rows), "min_available": min(r["available"] for r in rows),
              "app_ready": [l for l in lines1 + lines2 if l["stage"] == "app_ready"], "queue_end": [l for l in lines1 + lines2 if l["stage"] == "queue_end"],
              "zombie_ffmpeg": leftovers, "app_alive_after_close": app_alive, "outputs": outputs, "criticals": criticals, "windows_events": windows_events(since)}
    if len(table1) >= 2:
        report["delta_set1_set4_rss"] = table1[-1]["end_rss"] - table1[0]["end_rss"]; report["delta_set1_set4_private"] = table1[-1]["end_private"] - table1[0]["end_private"]
        report["delta_set1_set4_handles"] = table1[-1]["end_handles"] - table1[0]["end_handles"]; report["delta_set1_set4_threads"] = table1[-1]["end_threads"] - table1[0]["end_threads"]
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("app_ready", "queue_end")}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
