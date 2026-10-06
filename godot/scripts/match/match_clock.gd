class_name MatchClock
extends RefCounted
## Playing and physics clocks, including kickoff/half-time banners and local waits.

var state: String = "TITLE"
var game_time: float = 0.0
var simulation_elapsed: float = 0.0
var halftime_done: bool = false
var banner: String = ""
var banner_timer: float = 0.0


func advance(dt: float, restart_waiting: bool) -> String:
	simulation_elapsed += dt
	var banner_active: bool = banner_timer > 0
	if banner_active:
		banner_timer = maxf(0.0, banner_timer - dt)
	var kickoff_preview: bool = banner_active and banner == "KICK OFF" and game_time <= 0.0001
	if restart_waiting or kickoff_preview:
		return ""
	var rules: Dictionary = MatchProtocol.values()["kernel"] as Dictionary
	game_time += dt * (rules["clock_rate"] as float)
	var duration: float = rules["match_seconds"] as float
	if not halftime_done and game_time >= duration / 2.0 - 0.000001:
		halftime_done = true
		game_time = duration / 2.0
		banner = "HALF TIME"
		banner_timer = 2.4
		return "HALFTIME"
	if game_time >= duration - 0.000001:
		game_time = duration
		state = "FULLTIME"
		return "FULLTIME"
	return ""
