set g to (POSIX path of (path to home folder)) & "Desktop/Friday/gaming/clipper/guard/guard.sh"
tell application "OBS" to activate
delay 4
tell application "Terminal"
	activate
	do script quoted form of g & " --test"
end tell
