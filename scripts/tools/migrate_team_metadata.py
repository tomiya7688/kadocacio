from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT


TEAMS_ROOT = PROJECT_ROOT / "teams"
TARGET_FOLDERS = ("kadoka_original_A", "kadoka_original_B", "kadoka_original_E")

ABBREVIATIONS = {
    "AOBA UNITED": "AOBA",
    "LOAD SPIn": "LOAD",
    "トルテポルテ": "トルテ",
    "京都パープルズ": "京都パ",
    "仙台フォレスト": "仙台フ",
    "信州アルプス": "信州ア",
    "北海スノーフォックス": "北海ス",
    "千葉マリナーズ": "千葉マ",
    "名古屋シャチホコ": "名古屋",
    "夕張kadoka_japan": "夕張K",
    "川崎ブルーギア": "川崎ブ",
    "広島レッドアロー": "広島レ",
    "東京メトロスター": "東京メ",
    "横浜ベイウイング": "横浜ベ",
    "浦和レッドギア": "浦和レ",
    "甲府グレープス": "甲府グ",
    "神戸ハーバーズ": "神戸ハ",
    "私立蜜柑山学園": "蜜柑山",
    "越後スワンズ": "越後ス",
    "金沢ゴールドリーフ": "金沢ゴ",
    "多摩グリーンズ": "多摩グ",
    "大宮オレンジライン": "大宮オ",
    "奈良ディアーズ": "奈良デ",
    "富山マウンテンズ": "富山マ",
    "山形チェリーズ": "山形チ",
    "岐阜リバーバンク": "岐阜リ",
    "岡山ピーチボーイズ": "岡山ピ",
    "徳島ブルータイド": "徳島ブ",
    "札幌ノースゲート": "札幌ノ",
    "栃木サンダーズ": "栃木サ",
    "水戸レイクサイド": "水戸レ",
    "湘南シーブリーズ": "湘南シ",
    "熊本ファイアーズ": "熊本フ",
    "琉球サンゴ": "琉球サ",
    "盛岡グラナイト": "盛岡グ",
    "相模原スターズ": "相模原",
    "福島ピーチブロッサム": "福島ピ",
    "秋田ライスフィールド": "秋田ラ",
    "群馬ホットスプリング": "群馬ホ",
    "静岡ティーリーフ": "静岡テ",
    "負けチーム": "負け",
}


def default_description(name: str, folder_name: str) -> str:
    if folder_name == "kadoka_original_A":
        return (
            f"{name}は、カドカルチョ・オリジナルAを主戦場とする上位クラブです。"
            "高い基礎能力を土台に、それぞれの選手タイプとチーム戦術を組み合わせて頂点を狙います。"
            "リーグ戦では一つの形に固執せず、対戦相手と試合展開に応じた判断力も見どころです。"
        )
    if folder_name == "kadoka_original_B":
        return (
            f"{name}は、カドカルチョ・オリジナルBから上位カテゴリーを目指すクラブです。"
            "発展途上の部分を抱えながらも、地域色のあるチーム作りと粘り強い試合運びを大切にしています。"
            "選手の成長や補強によって、シーズンごとに戦い方が変わっていく余地を持っています。"
        )
    return (
        f"{name}は、試合バランスやAI挙動の確認に使えるデバッグ向けチームです。"
        "能力差が大きい対戦や特殊なフォーメーションを検証するときの基準として利用できます。"
    )


def migrate(*, dry_run: bool = False) -> list[Path]:
    changed: list[Path] = []
    for folder_name in TARGET_FOLDERS:
        folder = TEAMS_ROOT / folder_name
        for path in sorted(folder.glob("*.json"), key=lambda item: item.name.casefold()):
            raw = path.read_bytes()
            line_ending = "\r\n" if b"\r\n" in raw else "\n"
            payload = json.loads(raw.decode("utf-8-sig"))
            info = payload.setdefault("チーム情報", {})
            name = str(info.get("チーム名", path.stem))
            before = dict(info)
            info["チームの略称"] = ABBREVIATIONS.get(name, str(info.get("チームの略称", name[:3])))
            info.setdefault("チーム紹介", default_description(name, folder_name))
            if info == before:
                continue
            changed.append(path)
            if not dry_run:
                temporary = path.with_suffix(path.suffix + ".tmp")
                with temporary.open("w", encoding="utf-8", newline=line_ending) as file:
                    json.dump(payload, file, ensure_ascii=False, indent=2)
                    file.write("\n")
                temporary.replace(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Add team introductions and regional abbreviations.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    changed = migrate(dry_run=args.dry_run)
    print(f"{'Would update' if args.dry_run else 'Updated'} {len(changed)} team files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
