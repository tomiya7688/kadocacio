# {
#   責務: [BallSimulationSystem: 自由ボールの飛行・セーブ候補・境界・接触を参照順に更新する]
#   フィールド: [_save_resolver: セーブ成否の接続; _touch_resolver: 接触成否の接続; _resolver_owners: 接続先の寿命を保持する強参照]
# }
class_name BallSimulationSystem
extends RefCounted
## Flight -> keeper -> boundary -> touches. Unmigrated resolvers queue a barrier.

var _save_resolver: Callable
var _touch_resolver: Callable
var _resolver_owners: Array[RefCounted] = []


# {
#   責務: [connect_contacts: Nodeを持たない接触成否の処理を接続する]
#   処理: [1: 両Callableと所有者型を検査; 2: 成功時だけ接続と所有者参照を更新]
#   引数: [save_resolver: セーブ候補を処理するCallable; touch_resolver: 通常接触を処理するCallable]
#   戻り値: [bool: 両接続が有効ならtrue。失敗時は既存接続を保持]
# }
func connect_contacts(save_resolver: Callable, touch_resolver: Callable) -> bool:
	for resolver: Callable in [save_resolver, touch_resolver]:
		if not resolver.is_valid() or not resolver.get_object() is RefCounted:
			return false
	_save_resolver = save_resolver
	_touch_resolver = touch_resolver
	_resolver_owners.assign([save_resolver.get_object(), touch_resolver.get_object()])
	return true


# {
#   責務: [update: 通常プレイの自由ボールだけを進め、未移行の成否は障壁として返す]
#   処理: [1: 保持中と再開準備中を除外; 2: 飛行後にセーブ候補を処理; 3: 境界を処理; 4: 通常接触を処理]
#   引数: [state: 演算核が所有する試合状態; dt: 固定更新秒; rng: 接続した成否判定用の乱数]
#   戻り値: [void: ボールとイベントまたは未解決候補を更新。再開配置は他の更新段階に任せる]
# }
func update(state: MatchState, dt: float, rng: ObservedMatchRandom) -> void:
	if state.ball.owner != null or not state.restart.is_empty() or not state.throw_in.is_empty():
		return
	BallFlightSystem.update(state.ball, dt)
	var save: BallContactCandidate = BallContactQuery.save_candidate(state)
	if save != null:
		if not _save_resolver.is_valid():
			state.ball_contact = save
			return
		if _save_resolver.call(state, save, rng) as bool:
			return
	var outcome: String = state.ball.shot_outcome
	var event: BallBoundaryEvent = BallBoundarySystem.detect(state)
	if event != null:
		if event.kind == "POST":
			state.events.append((state.ball.last_touch.definition.name if state.ball.last_touch != null else "シュート") + "はポスト！", state.clock)
		else:
			state.ball_boundary = event
			if event.kind in ["GOAL_KICK", "CORNER_KICK"] and not state.ball.shot_miss_announced and outcome in ["WIDE", "OVER"]:
				state.ball.shot_miss_announced = true
				var shooter: String = state.ball.last_touch.definition.name if state.ball.last_touch != null else "シュート"
				state.events.append(shooter + ("のシュートはゴールの外" if outcome == "WIDE" else "のシュートはバーの上"), state.clock)
		return
	for candidate: BallContactCandidate in BallContactQuery.touches(state):
		if not _touch_resolver.is_valid():
			state.ball_contact = candidate
			return
		if _touch_resolver.call(state, candidate, rng) as bool:
			return
