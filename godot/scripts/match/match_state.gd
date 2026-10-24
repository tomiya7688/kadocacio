class_name MatchState
extends RefCounted
## Mutable engine-owned state; callers obtain MatchSnapshot copies instead.

var home: TeamState
var away: TeamState
var ball: BallState = BallState.new()
var clock: MatchClock = MatchClock.new()
var events: MatchEventLog = MatchEventLog.new()
var step: int = 0
var paused: bool = false
var speed_multiplier: int = 1
var max_steps: int
var venue_mode: String
var ai_rethink_multiplier: float
var restart: Dictionary = {}
var throw_in: Dictionary = {}
var pending_kick: Dictionary = {}
var foul_count: int = 0
var card_count: int = 0
var restart_counts: Dictionary = {"THROW_IN": 0, "FREE_KICK": 0, "PENALTY_KICK": 0, "GOAL_KICK": 0, "CORNER_KICK": 0}
