# Clipper — best moments + Expectation vs Reality Shorts

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
