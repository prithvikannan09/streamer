# Streamer (with Clipper added)

Folder: ~/Desktop/Friday/gaming/clipper   (run commands from Terminal with ./run.sh)

## 1. Approve a streamer (only ones who allow clipping)
./run.sh add-streamer NAME --credit "twitch.tv/NAME" --permission "link or note where they allow clipping"
./run.sh streamers

## 2. Find best moments
Your own recording:      ./run.sh find "~/Movies/2026-11-19 10-00-00.mp4"
YouTube stream/video:    ./run.sh find "https://www.youtube.com/watch?v=..." --streamer NAME
Twitch VOD:              ./run.sh find "https://www.twitch.tv/videos/..." --streamer NAME
Twitch top clips (7d):   ./run.sh find "https://www.twitch.tv/NAME/clips?filter=clips&range=7d" --streamer NAME
Options: --top 10 (how many), --before 20 --after 10 (seconds around each moment)

How moments are found: YouTube "most replayed" data when available, Twitch clip view counts,
otherwise loudness spikes (your reactions + big game sounds).
Output: clips/<name>/ with one .mp4 per moment + contact_sheet.jpg (numbered preview).

## 3. Make an Expectation vs Reality Short (9:16, under 60s)
./run.sh eor clips/me/A.mp4 clips/me/B.mp4 --e-start 12 --e-dur 6 --r-start 15 --r-dur 9 \
   --e-caption "me thinking im a pro" --r-caption "semma fail da"
Add --own if a clip is your own footage that didn't come from 'find'.
Output: shorts/eor_....mp4 — credit is burned in for other streamers; ALSO put it in the description.

Rules built in: refuses unapproved streamers, refuses Shorts over 60s, loudness normalised for Shorts.

## The app (no Terminal needed)
Double-click Clipper on the Desktop. Menu:
- Find best moments in my recording -> pick a file from Movies -> numbered preview sheet + clips folder open
- Find best moments from a stream link -> pick approved streamer, paste link
- Make Expectation vs Reality Short -> pick 2 clips, type captions -> Short opens in QuickTime
- Add an approved streamer -> name, credit, link showing they allow clipping
- Open Shorts folder
Clips start at the detected moment automatically. App source: Clipper.applescript (rebuild: osacompile -o ~/Desktop/Clipper.app Clipper.applescript)

## 18+ safety
- clipper scan VIDEO  -> flags nudity (NudeNet, runs locally), pixelated preview sheet
- clipper clean VIDEO --mode cut|blur -> removes or blurs flagged parts
- Shorts (eor) auto-blur any flagged frames

## Stream Guard (live)
Desktop app "Stream Guard": opens OBS + a Terminal that watches the game through OBS's hidden
"Stream Guard Eye" source. On nudity it switches the program to the "18+ Privacy" scene (mic stays on,
game sound hidden), back after 3s clean. Viewers' picture is delayed 500 ms (Render Delay filter + audio
sync offset) so the cover lands first. Events logged in guard/logs/. "Stream Guard TEST" = faces count as 18+.
Setup script: guard/setup_obs.py (OBS must be closed). OBS WebSocket password stays in OBS's own config.

## Live streaming setup (OBS 33 + PS Remote Play, Mac)
- Scene "GTA 6 Live": whole-screen capture of the Remote Play window (crop 240 top / 134 bottom),
  500 ms Render Delay so Stream Guard reacts before viewers see a frame; game audio +500 ms to match.
- Facecam: MacBook camera, top-right round bubble with yellow ring; Background Removal plugin
  (obs-backgroundremoval 1.4.1) blurs the room; crop + circle mask filters.
- "18+ Privacy" scene: "18+ SCENE SKIPPED" card, facecam and mic stay on, game hidden.
- Stream Guard (guard/guard.py), medium mode: --threshold 0.35 --hold 5; weak hits must repeat within ~1 s,
  scores >= 0.5 hide instantly. Watches the undelayed "Stream Guard Eye" source via OBS WebSocket,
  auto-reconnects if OBS restarts, starts/stops recording with the stream, opens live chat when you go live.
- Live chat: guard/livechat.sh finds the current live video on @arunthewall and opens guard/chatwin,
  a small always-on-top chat window (also works over full-screen Remote Play). Build: swiftc -O chatwin.swift -o chatwin
- Rules while live: Do Not Disturb on, only Remote Play on the Mac screen (OBS shows the whole screen).
