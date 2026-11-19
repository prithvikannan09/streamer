import CoreGraphics
let want = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Remote Play"
let l = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as! [[String:Any]]
var best: (Int, Double) = (0, 0)
for w in l {
    let owner = w["kCGWindowOwnerName"] as? String ?? ""
    guard owner.contains(want), (w["kCGWindowLayer"] as? Int ?? 1) == 0 else { continue }
    let b = w["kCGWindowBounds"] as! [String:Any]
    let area = (b["Width"] as? Double ?? 0) * (b["Height"] as? Double ?? 0)
    if area > best.1 { best = (w["kCGWindowNumber"] as! Int, area) }
}
if best.0 > 0 { print(best.0) }
