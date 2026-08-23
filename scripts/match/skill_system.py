from __future__ import annotations

import random

from scripts.match.player_commands import PlayerCommand


AERIAL_HEADER = "エアリアルヘッド"
SLIDE_FINISH = "スライドフィニッシュ"
ARC_CURVE = "アークカーブ"
WOBBLE_BALL = "揺らぎ弾"
CHANCE_SENSOR = "決定機センサー"
MAGIC_PLACE_KICK = "魔術師のプレースキック"
FORTRESS_BLOCK = "城塞ブロック"
SPIN_TURN = "スピンターン"
CLOSE_LOCK = "密着封鎖"
VACANT_COVER = "空白カバー"
BACKLINE_HUNTER = "背後の狩人"
PIVOT_KEEP = "楔のキープ"
ONE_TOUCH_RELAY = "ワンタッチリレー"
CARRY_SHOT = "キャリーショット"
UNBREAKABLE_HEART = "不屈の心"
OVERLOAD = "オーバーロード"
RECOVERY_CHASE = "リカバリーチェイス"
TURNOVER_COUNTER = "奪取カウンター"
HEEL_REVERSE_TURN = "反転ヒールターン"
STABLE_CORE = "不動の体幹"
OVERHEAD_VOLLEY = "オーバーヘッドボレー"
HALFWAY_CANNON = "ハーフウェイ砲"
TIGHT_TOUCH = "タイトタッチ"
SPRINT_CARRY = "スプリントキャリー"
ENERGY_KEEP = "エナジーキープ"
COOLDOWN_REST = "クールダウン休息"
POWER_SLIDE = "パワースライド"
ONE_WAY_BLOCK = "片道封鎖"
BLIND_FEED = "ブラインドフィード"
SIGNAL_LINK = "サイン連携"
LAST_CHANCE_CANNON = "ラストチャンス砲"
SAVING_AURA = "セービングオーラ"
EARLY_READ_SAVE = "先読みセーブ"
CANNON_MIDDLE = "キャノンミドル"
DIRECT_VOLLEY = "ダイレクトボレー"
SET_AND_SHOOT = "セット＆シュート"
ILLUSION_STEP = "幻惑ステップ"
RELENTLESS_PRESS = "猛追プレス"
FUTURE_READ = "フューチャーリード"
SWEEPER_KEEPER = "スイーパーキーパー"

ALL_SKILLS = (
    AERIAL_HEADER,
    SLIDE_FINISH,
    ARC_CURVE,
    WOBBLE_BALL,
    CHANCE_SENSOR,
    MAGIC_PLACE_KICK,
    FORTRESS_BLOCK,
    SPIN_TURN,
    CLOSE_LOCK,
    VACANT_COVER,
    BACKLINE_HUNTER,
    PIVOT_KEEP,
    ONE_TOUCH_RELAY,
    CARRY_SHOT,
    UNBREAKABLE_HEART,
    OVERLOAD,
    RECOVERY_CHASE,
    TURNOVER_COUNTER,
    HEEL_REVERSE_TURN,
    STABLE_CORE,
    OVERHEAD_VOLLEY,
    HALFWAY_CANNON,
    TIGHT_TOUCH,
    SPRINT_CARRY,
    ENERGY_KEEP,
    COOLDOWN_REST,
    POWER_SLIDE,
    ONE_WAY_BLOCK,
    BLIND_FEED,
    SIGNAL_LINK,
    LAST_CHANCE_CANNON,
    SAVING_AURA,
    EARLY_READ_SAVE,
    CANNON_MIDDLE,
    DIRECT_VOLLEY,
    SET_AND_SHOOT,
    ILLUSION_STEP,
    RELENTLESS_PRESS,
    FUTURE_READ,
    SWEEPER_KEEPER,
)

# Older custom teams remain loadable after the public-facing names changed.
LEGACY_SKILL_ALIASES = dict(zip((
    "ヘディングシュート", "スライディングシュート", "バナナシュート", "ナックルシュート",
    "ゴールの嗅覚", "伝説のフリーキック", "カテナチオ", "マルセイユルーレット",
    "鉄壁のマンツーマンディフェンス", "カバーリング", "シャドーストライカー", "ポストプレー",
    "ダイレクトパス", "ドリブルシュート", "スティールハート", "数的優位", "チェイシング",
    "反転速攻", "クライフターン", "鋼のボディ", "バイシクルシュート", "超ロングシュート",
    "カミソリドリブル", "高速ドリブル", "タフネスダイナモ", "ウルトラリラックス",
    "必殺スライディング", "ワンサイドカット", "ノールックパス", "アイコンタクト",
    "ブザービート", "ゴールの守護神", "スーパーセーブ", "強烈ミドルシュート",
    "ボレーシュート", "ワントラップシュート", "トリッキーフェイント", "鬼プレス",
    "シミュレーション", "ゴールキーパーの攻撃参加",
), ALL_SKILLS))


def normalize_skill_name(value: object) -> str:
    name = str(value).strip()
    return LEGACY_SKILL_ALIASES.get(name, name)

SKILL_COMMAND = {
    AERIAL_HEADER: PlayerCommand.SKILL_AERIAL_HEADER,
    SLIDE_FINISH: PlayerCommand.SKILL_SLIDE_FINISH,
    ARC_CURVE: PlayerCommand.SKILL_ARC_CURVE,
    WOBBLE_BALL: PlayerCommand.SKILL_WOBBLE_BALL,
    CHANCE_SENSOR: PlayerCommand.SKILL_CHANCE_SENSOR,
    MAGIC_PLACE_KICK: PlayerCommand.SKILL_MAGIC_PLACE_KICK,
    FORTRESS_BLOCK: PlayerCommand.SKILL_FORTRESS_BLOCK,
    SPIN_TURN: PlayerCommand.SKILL_SPIN_TURN,
    CLOSE_LOCK: PlayerCommand.SKILL_CLOSE_LOCK,
    VACANT_COVER: PlayerCommand.SKILL_VACANT_COVER,
    BACKLINE_HUNTER: PlayerCommand.SKILL_BACKLINE_HUNTER,
    PIVOT_KEEP: PlayerCommand.SKILL_PIVOT_KEEP,
    ONE_TOUCH_RELAY: PlayerCommand.SKILL_ONE_TOUCH_RELAY,
    CARRY_SHOT: PlayerCommand.SKILL_CARRY_SHOT,
    UNBREAKABLE_HEART: PlayerCommand.SKILL_UNBREAKABLE_HEART,
    OVERLOAD: PlayerCommand.SKILL_OVERLOAD,
    RECOVERY_CHASE: PlayerCommand.SKILL_RECOVERY_CHASE,
    TURNOVER_COUNTER: PlayerCommand.SKILL_TURNOVER_COUNTER,
    HEEL_REVERSE_TURN: PlayerCommand.SKILL_HEEL_REVERSE_TURN,
    STABLE_CORE: PlayerCommand.SKILL_STABLE_CORE,
    OVERHEAD_VOLLEY: PlayerCommand.SKILL_OVERHEAD_VOLLEY,
    HALFWAY_CANNON: PlayerCommand.SKILL_HALFWAY_CANNON,
    TIGHT_TOUCH: PlayerCommand.SKILL_TIGHT_TOUCH,
    SPRINT_CARRY: PlayerCommand.SKILL_SPRINT_CARRY,
    ENERGY_KEEP: PlayerCommand.SKILL_ENERGY_KEEP,
    COOLDOWN_REST: PlayerCommand.SKILL_COOLDOWN_REST,
    POWER_SLIDE: PlayerCommand.SKILL_POWER_SLIDE,
    ONE_WAY_BLOCK: PlayerCommand.SKILL_ONE_WAY_BLOCK,
    BLIND_FEED: PlayerCommand.SKILL_BLIND_FEED,
    SIGNAL_LINK: PlayerCommand.SKILL_SIGNAL_LINK,
    LAST_CHANCE_CANNON: PlayerCommand.SKILL_LAST_CHANCE_CANNON,
    SAVING_AURA: PlayerCommand.SKILL_SAVING_AURA,
    EARLY_READ_SAVE: PlayerCommand.SKILL_EARLY_READ_SAVE,
    CANNON_MIDDLE: PlayerCommand.SKILL_CANNON_MIDDLE,
    DIRECT_VOLLEY: PlayerCommand.SKILL_DIRECT_VOLLEY,
    SET_AND_SHOOT: PlayerCommand.SKILL_SET_AND_SHOOT,
    ILLUSION_STEP: PlayerCommand.SKILL_ILLUSION_STEP,
    RELENTLESS_PRESS: PlayerCommand.SKILL_RELENTLESS_PRESS,
    FUTURE_READ: PlayerCommand.SKILL_FUTURE_READ,
    SWEEPER_KEEPER: PlayerCommand.SKILL_SWEEPER_KEEPER,
}

SKILL_COOLDOWN = {
    AERIAL_HEADER: 3.0,
    SLIDE_FINISH: 4.0,
    ARC_CURVE: 2.4,
    WOBBLE_BALL: 2.4,
    CHANCE_SENSOR: 1.8,
    MAGIC_PLACE_KICK: 8.0,
    FORTRESS_BLOCK: 12.0,
    SPIN_TURN: 5.0,
    CLOSE_LOCK: 4.0,
    VACANT_COVER: 16.0,
    BACKLINE_HUNTER: 18.0,
    PIVOT_KEEP: 8.0,
    ONE_TOUCH_RELAY: 7.0,
    CARRY_SHOT: 10.0,
    UNBREAKABLE_HEART: 24.0,
    OVERLOAD: 18.0,
    RECOVERY_CHASE: 14.0,
    TURNOVER_COUNTER: 22.0,
    HEEL_REVERSE_TURN: 8.0,
    STABLE_CORE: 18.0,
    OVERHEAD_VOLLEY: 18.0,
    HALFWAY_CANNON: 20.0,
    TIGHT_TOUCH: 9.0,
    SPRINT_CARRY: 10.0,
    ENERGY_KEEP: 16.0,
    COOLDOWN_REST: 45.0,
    POWER_SLIDE: 18.0,
    ONE_WAY_BLOCK: 15.0,
    BLIND_FEED: 8.0,
    SIGNAL_LINK: 7.0,
    LAST_CHANCE_CANNON: 999.0,
    SAVING_AURA: 18.0,
    EARLY_READ_SAVE: 26.0,
    CANNON_MIDDLE: 16.0,
    DIRECT_VOLLEY: 12.0,
    SET_AND_SHOOT: 12.0,
    ILLUSION_STEP: 9.0,
    RELENTLESS_PRESS: 16.0,
    FUTURE_READ: 90.0,
    SWEEPER_KEEPER: 38.0,
}

# Strong match-changing skills are deliberately rarer than small positional skills.
SKILL_ACTIVATION_WEIGHT = {
    skill: 0.72 for skill in ALL_SKILLS
}
SKILL_ACTIVATION_WEIGHT.update({
    MAGIC_PLACE_KICK: 0.34,
    FORTRESS_BLOCK: 0.45,
    VACANT_COVER: 0.34,
    BACKLINE_HUNTER: 0.30,
    CARRY_SHOT: 0.48,
    UNBREAKABLE_HEART: 0.32,
    TURNOVER_COUNTER: 0.34,
    STABLE_CORE: 0.30,
    OVERHEAD_VOLLEY: 0.24,
    HALFWAY_CANNON: 0.22,
    OVERLOAD: 0.42,
    RECOVERY_CHASE: 0.40,
    COOLDOWN_REST: 0.18,
    POWER_SLIDE: 0.25,
    ONE_WAY_BLOCK: 0.38,
    LAST_CHANCE_CANNON: 0.18,
    SAVING_AURA: 0.30,
    EARLY_READ_SAVE: 0.16,
    CANNON_MIDDLE: 0.26,
    DIRECT_VOLLEY: 0.35,
    SET_AND_SHOOT: 0.42,
    ILLUSION_STEP: 0.46,
    RELENTLESS_PRESS: 0.30,
    FUTURE_READ: 0.004,
    SWEEPER_KEEPER: 0.08,
})


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalized_skills(raw_skills: object) -> frozenset[str]:
    if not isinstance(raw_skills, list):
        return frozenset()
    normalized = (normalize_skill_name(value) for value in raw_skills)
    return frozenset(value for value in normalized if value in SKILL_COMMAND)


def activation_probability(
    intelligence: float,
    situation_quality: float,
    execution_quality: float,
) -> float:
    """Intelligence increases opportunity selection, not blind skill frequency."""
    intelligence = clamp01(intelligence)
    situation_quality = clamp01(situation_quality)
    execution_quality = clamp01(execution_quality)
    # A smart player is more willing in a genuinely good situation, but applies
    # a steeper suitability gate to poor situations. Low intelligence has weak
    # discrimination and may occasionally try a skill at the wrong moment.
    discernment_exponent = 1.0 + intelligence * 1.35
    situation_gate = situation_quality ** discernment_exponent
    probability = (0.12 + intelligence * 0.78) * situation_gate
    probability *= 0.58 + execution_quality * 0.42
    return clamp01(probability)


def should_activate(
    held_skills: frozenset[str],
    cooldowns: dict[str, float],
    skill: str,
    intelligence: float,
    situation_quality: float,
    execution_quality: float,
    rng: random.Random,
) -> bool:
    if skill not in held_skills or cooldowns.get(skill, 0.0) > 0.0:
        return False
    probability = activation_probability(
        intelligence,
        situation_quality,
        execution_quality,
    )
    probability *= SKILL_ACTIVATION_WEIGHT.get(skill, 0.65)
    return rng.random() < probability
