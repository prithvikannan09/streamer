set clipperDir to (POSIX path of (path to home folder)) & "Desktop/Friday/gaming/clipper"
set runSh to quoted form of (clipperDir & "/run.sh")
set actions to {"Find best moments in my recording", "Find best moments from a stream link", "Auto-clip top GTA 6 YouTube videos (for EXPECTATION)", "Make Expectation vs Reality Short", "Add an approved streamer", "Open Shorts folder"}
set picked to choose from list actions with title "Clipper" with prompt "What do you want to do?" default items {item 1 of actions}
if picked is false then return
set picked to item 1 of picked

if picked is item 1 of actions then
	set f to choose file with prompt "Pick your recording" default location (path to movies folder)
	set n to text returned of (display dialog "How many moments should I find?" default answer "10" with title "Clipper")
	display notification "Scanning your recording. This takes a minute or two." with title "Clipper"
	my runAndShowSheet(runSh & " find " & quoted form of POSIX path of f & " --top " & n)

else if picked is item 2 of actions then
	set names to paragraphs of (do shell script runSh & " streamers --names")
	if names is {} or names is {""} then
		display dialog "No approved streamers yet. Use 'Add an approved streamer' first (only streamers who allow clipping)." with title "Clipper" buttons {"OK"}
		return
	end if
	set who to choose from list names with title "Clipper" with prompt "Whose stream is it?"
	if who is false then return
	set link to text returned of (display dialog "Paste the YouTube or Twitch link:" default answer "" with title "Clipper")
	set n to text returned of (display dialog "How many moments should I find?" default answer "8" with title "Clipper")
	display notification "Finding the best moments. Long streams can take a few minutes." with title "Clipper"
	my runAndShowSheet(runSh & " find " & quoted form of link & " --streamer " & quoted form of (item 1 of who) & " --top " & n)

else if picked is item 3 of actions then
	set q to text returned of (display dialog "What should I search YouTube for?" default answer "gta 6 gameplay" with title "Clipper")
	set nv to text returned of (display dialog "How many videos to clip from?" default answer "3" with title "Clipper")
	display notification "Searching YouTube and clipping free-to-reuse videos. This takes a few minutes." with title "Clipper"
	try
		set out to do shell script runSh & " auto --query " & quoted form of q & " --videos " & nv & " 2>&1"
	on error errText
		my showProblem(errText)
		return
	end try
	set sheetPath to my valueOf(out, "SHEET=")
	if sheetPath is not "" then do shell script "open " & quoted form of sheetPath
	set i0 to offset of "Top channels" in out
	set summary to out
	if i0 > 0 then set summary to text i0 thru -1 of out
	if (length of summary) > 900 then set summary to text 1 thru 900 of summary
	display dialog summary with title "Clipper - done" buttons {"OK"}

else if picked is item 4 of actions then
	set clipsFolder to POSIX file (clipperDir & "/clips") as alias
	set e to choose file with prompt "Pick the EXPECTATION clip (the epic one)" default location clipsFolder
	set r to choose file with prompt "Pick the REALITY clip (your fail)" default location clipsFolder
	set ec to text returned of (display dialog "Caption for EXPECTATION (Tanglish ok, no emoji):" default answer "" with title "Clipper")
	set rc to text returned of (display dialog "Caption for REALITY:" default answer "" with title "Clipper")
	set cmd to runSh & " eor " & quoted form of POSIX path of e & " " & quoted form of POSIX path of r & " --e-caption " & quoted form of ec & " --r-caption " & quoted form of rc
	display notification "Making your Short..." with title "Clipper"
	try
		set out to do shell script cmd & " 2>&1"
	on error errText
		if errText contains "add --own" then
			set ans to button returned of (display dialog "One of these clips didn't come from Clipper. Is it your own gameplay?" buttons {"No", "Yes, it's mine"} default button 2 with title "Clipper")
			if ans is "No" then
				display dialog "Then get it through 'Find best moments from a stream link' so the streamer gets credit." with title "Clipper" buttons {"OK"}
				return
			end if
			try
				set out to do shell script cmd & " --own 2>&1"
			on error errText2
				my showProblem(errText2)
				return
			end try
		else
			my showProblem(errText)
			return
		end if
	end try
	set outPath to my valueOf(out, "OUTPUT=")
	if outPath is not "" then do shell script "open -a 'QuickTime Player' " & quoted form of outPath
	display notification "Short ready! Opened in QuickTime." with title "Clipper"

else if picked is item 5 of actions then
	set nm to text returned of (display dialog "Streamer name (one word, e.g. their Twitch name):" default answer "" with title "Clipper")
	set cr to text returned of (display dialog "Credit to show on the Short:" default answer "twitch.tv/" & nm with title "Clipper")
	set pm to text returned of (display dialog "Paste the link or note showing they ALLOW clipping:" default answer "" with title "Clipper")
	try
		set res to do shell script runSh & " add-streamer " & quoted form of nm & " --credit " & quoted form of cr & " --permission " & quoted form of pm & " 2>&1"
		display dialog res with title "Clipper" buttons {"OK"}
	on error errText
		my showProblem(errText)
	end try

else
	do shell script "mkdir -p " & quoted form of (clipperDir & "/shorts") & "; open " & quoted form of (clipperDir & "/shorts")
end if

on runAndShowSheet(cmd)
	try
		set out to do shell script cmd & " 2>&1"
	on error errText
		my showProblem(errText)
		return
	end try
	set sheetPath to my valueOf(out, "SHEET=")
	if sheetPath is not "" then
		do shell script "open " & quoted form of sheetPath
		do shell script "open " & quoted form of (do shell script "dirname " & quoted form of sheetPath)
	end if
	display notification "Done! The numbered preview sheet is open." with title "Clipper"
end runAndShowSheet

on valueOf(txt, key)
	repeat with ln in paragraphs of txt
		if ln starts with key then return text ((length of key) + 1) thru -1 of ln
	end repeat
	return ""
end valueOf

on showProblem(errText)
	set msg to errText
	if msg contains "STOP:" then set msg to text ((offset of "STOP:" in msg) + 6) thru -1 of msg
	if (length of msg) > 600 then set msg to text 1 thru 600 of msg
	display dialog msg with title "Clipper - problem" buttons {"OK"} with icon caution
end showProblem
