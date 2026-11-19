import json, os, shutil, uuid, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OBS = Path.home() / "Library/Application Support/obs-studio"
SCENES = OBS / "basic/scenes/Untitled.json"
WS = OBS / "plugin_config/obs-websocket/config.json"
HERE = Path(__file__).resolve().parent
BACKUP = OBS / "basic.backup-before-gta6-20261118"

card = HERE / "privacy_card.png"
im = Image.new("RGB", (1920, 1080), (14, 12, 16))
d = ImageDraw.Draw(im)
for r in range(900, 0, -60):
    d.ellipse([960 - r, 540 - r, 960 + r, 540 + r], outline=(32, 26, 30), width=10)
im = im.filter(ImageFilter.GaussianBlur(2))
d = ImageDraw.Draw(im)
bebas = ImageFont.truetype(os.path.expanduser("~/Library/Fonts/BebasNeue-Bold.ttf"), 230)
inter = ImageFont.truetype(os.path.expanduser("~/Library/Fonts/Inter-Black.otf"), 64)
small = ImageFont.truetype(os.path.expanduser("~/Library/Fonts/Inter-Black.otf"), 44)
d.text((960, 430), "18+ SCENE SKIPPED", font=bebas, fill=(255, 212, 0), anchor="mm", stroke_width=12, stroke_fill="black")
d.text((960, 620), "keeping the channel clean - back in a sec", font=inter, fill="white", anchor="mm", stroke_width=6, stroke_fill="black")
d.text((960, 960), "@arunthewall", font=small, fill=(150, 150, 150), anchor="mm")
im.save(card)

shutil.copy(SCENES, BACKUP / f"Untitled.before-streamguard.json")
data = json.loads(SCENES.read_text())
src = {s["name"]: s for s in data["sources"]}
tmpl = src["macOS Screen Capture"]
base = {k: v for k, v in tmpl.items() if k not in ("filters", "hotkeys", "settings", "private_settings")}

if "18+ Privacy Card" not in src:
    img = dict(base, name="18+ Privacy Card", uuid=str(uuid.uuid4()), id="image_source", versioned_id="image_source",
               settings={"file": str(card)}, mixers=0)
    data["sources"].append(img)
    scene_tmpl = src["Zoom Recording"]
    item = dict(scene_tmpl["settings"]["items"][0])
    item.update(name="18+ Privacy Card", source_uuid=img["uuid"], id=1, locked=True, visible=True, pos={"x": 0.0, "y": 0.0},
                scale={"x": 1.0, "y": 1.0}, bounds_type=0, crop_top=0, crop_bottom=0, crop_left=0, crop_right=0)
    for k in ("pos_rel", "scale_rel", "bounds_rel"):
        item.pop(k, None)
    scene = dict(scene_tmpl, name="18+ Privacy", uuid=str(uuid.uuid4()),
                 settings={"id_counter": 1, "custom_size": False, "items": [item]})
    data["sources"].append(scene)
    data["scene_order"].append({"name": "18+ Privacy"})

video = src["PS Remote Play - Video"]
if not any(f.get("id") == "gpu_delay" for f in video.get("filters", [])):
    flt = dict(base, name="Stream Guard delay", uuid=str(uuid.uuid4()), id="gpu_delay", versioned_id="gpu_delay",
               settings={"delay_ms": 500}, mixers=0)
    video.setdefault("filters", []).append(flt)
src["PS Remote Play - Game Audio"]["sync"] = 500_000_000
if "Stream Guard Eye" not in src:
    eye = dict(base, name="Stream Guard Eye", uuid=str(uuid.uuid4()), id=video["id"], versioned_id=video["versioned_id"],
               settings=dict(video["settings"]), mixers=0, muted=True, private_settings={"mixer_hidden": True})
    data["sources"].append(eye)
    gscene = src["GTA 6 Live"]
    vitem = next(i for i in gscene["settings"]["items"] if i["name"] == "PS Remote Play - Video")
    eitem = dict(vitem, name="Stream Guard Eye", source_uuid=eye["uuid"], id=gscene["settings"]["id_counter"] + 1, locked=True)
    gscene["settings"]["id_counter"] += 1
    gscene["settings"]["items"].insert(0, eitem)
data["current_scene"] = data["current_program_scene"] = "GTA 6 Live"
SCENES.write_text(json.dumps(data, indent=4))

ws = json.loads(WS.read_text())
ws["server_enabled"] = True
ws["auth_required"] = True
if not ws.get("server_password"):
    import secrets
    ws["server_password"] = secrets.token_urlsafe(16)
WS.write_text(json.dumps(ws, indent=4))
print("obs configured: privacy scene, 500ms picture delay, game audio +500ms, websocket on (password kept private)")
