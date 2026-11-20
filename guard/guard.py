import argparse, base64, datetime, json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = Path.home() / "Library/Application Support/obs-studio/plugin_config/obs-websocket/config.json"
STRICT_EXTRA = {"FEMALE_BREAST_COVERED", "BUTTOCKS_COVERED", "FEMALE_GENITALIA_COVERED"}
SENSITIVE = {"FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED", "BUTTOCKS_EXPOSED", "ANUS_EXPOSED"}


def say(msg):
    print(f"{datetime.datetime.now():%H:%M:%S}  {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-scene", default="GTA 6 Live")
    ap.add_argument("--privacy-scene", default="18+ Privacy")
    ap.add_argument("--eye", default="Stream Guard Eye", help="OBS source with the undelayed game picture")
    ap.add_argument("--threshold", type=float, default=0.30)
    ap.add_argument("--hold", type=float, default=8.0, help="seconds of clean frames before showing the game again")
    ap.add_argument("--classes", default="")
    ap.add_argument("--test", action="store_true", help="treat FACES as 18+ so you can see the switch work")
    ap.add_argument("--strict", action="store_true", help="also hide lingerie/pole-dance frames (covers beach swimwear too)")
    a = ap.parse_args()
    classes = set(a.classes.split(",")) if a.classes else SENSITIVE
    if a.test:
        classes, a.threshold = {"FACE_FEMALE", "FACE_MALE"}, 0.30
        say("TEST MODE: faces count as 18+. Show a character's face up close in-game and the 18+ screen should appear.")

    import obsws_python as obs
    from nudenet import NudeDetector
    def connect(wait=True):
        said = False
        while True:
            try:
                cfg = json.loads(WS.read_text())
                return obs.ReqClient(host="localhost", port=cfg["server_port"],
                                     password=cfg["server_password"] if cfg.get("auth_required") else "", timeout=3)
            except Exception:
                if not wait:
                    raise
                if not said:
                    say("Waiting for OBS... (open OBS; I'll connect automatically)")
                    said = True
                time.sleep(2)

    cl = connect()
    det = NudeDetector()
    logdir = HERE / "logs"
    logdir.mkdir(exist_ok=True)
    log = logdir / f"{datetime.date.today()}.jsonl"
    shot = Path("/tmp/streamguard.jpg")

    def scene(name):
        try:
            cl.set_current_program_scene(name)
        except Exception as e:
            say(f"OBS scene switch failed: {e}")

    def timecode():
        out = {}
        for k, fn in (("record", cl.get_record_status), ("stream", cl.get_stream_status)):
            try:
                r = fn()
                if r.output_active:
                    out[k] = r.output_timecode
            except Exception:
                pass
        return out

    def stop(*_):
        if hidden:
            scene(a.game_scene)
        say("Stream Guard stopped.")
        sys.exit(0)

    hidden, last_hit, missing_said = False, 0.0, False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    scene(a.game_scene)
    say(f"Stream Guard ON. Watching the game through OBS. Leave this window open; close it to stop.")
    rec_check, we_started_rec = 0.0, False
    while True:
        t0 = time.time()
        if t0 - rec_check > 3:
            rec_check = t0
            try:
                live = cl.get_stream_status().output_active
                rec = cl.get_record_status().output_active
                if live and not rec:
                    cl.start_record()
                    we_started_rec = True
                    say("You're LIVE -> recording started automatically")
                elif not live and rec and we_started_rec:
                    cl.stop_record()
                    we_started_rec = False
                    say("Stream ended -> recording stopped and saved to Movies")
            except Exception:
                pass
        try:
            r = cl.get_source_screenshot(a.eye, "jpg", 640, 360, 75)
            shot.write_bytes(base64.b64decode(r.image_data.split(",", 1)[1]))
            ok = True
        except Exception:
            ok = False
        if not ok:
            try:
                cl.get_version()
            except Exception:
                say("Lost OBS (restarted or closed). Reconnecting...")
                cl = connect()
                say("Reconnected to OBS.")
                if hidden:
                    scene(a.privacy_scene)
                continue
            if not missing_said:
                say(f"Can't get the picture from OBS source '{a.eye}'.")
                missing_said = True
            time.sleep(0.5)
            continue
        missing_said = False
        found = det.detect(str(shot))
        hits = [d for d in found if d["class"] in classes and d["score"] >= a.threshold]
        if a.strict and not a.test:
            hits += [d for d in found if d["class"] in STRICT_EXTRA and d["score"] >= 0.50]
        now = time.time()
        if hits:
            last_hit = now
            if not hidden:
                scene(a.privacy_scene)
                hidden = True
                what = sorted({d["class"] for d in hits})
                say(f"18+ DETECTED -> stream hidden ({', '.join(what)})")
                with log.open("a") as f:
                    f.write(json.dumps({"event": "hide", "at": datetime.datetime.now().isoformat(), "what": what, **timecode()}) + "\n")
            shot.unlink(missing_ok=True)
        elif hidden and now - last_hit >= a.hold:
            scene(a.game_scene)
            hidden = False
            say("Clean again -> game back on stream")
            with log.open("a") as f:
                f.write(json.dumps({"event": "show", "at": datetime.datetime.now().isoformat(), **timecode()}) + "\n")
        loop_ms = (time.time() - t0) * 1000
        if loop_ms > 450:
            say(f"warning: check took {loop_ms:.0f} ms (should be under 450)")
        time.sleep(max(0.0, 0.2 - (time.time() - t0)))


if __name__ == "__main__":
    main()
