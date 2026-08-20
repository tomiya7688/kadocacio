from __future__ import annotations

import pygame

from settings import CREAM, GOLD, HEIGHT, HOME_RED, INK, MUTED, PAPER, WIDTH


def build_team_folder_rows(teams: list[dict]) -> list[dict]:
    """Build fixed-height display rows grouped by the JSON's teams subfolder."""
    grouped: dict[str, list[dict]] = {}
    for team in teams:
        source = str(team.get("source", "")).replace("\\", "/").strip("/")
        folder = source.rsplit("/", 1)[0] if "/" in source else "teams直下"
        grouped.setdefault(folder, []).append(team)
    rows: list[dict] = []
    for folder in sorted(grouped, key=lambda value: (value == "teams直下", value.casefold())):
        folder_teams = sorted(grouped[folder], key=lambda choice: str(choice.get("name", "")).casefold())
        rows.append({"kind": "folder", "folder": folder, "teams": folder_teams})
        for index in range(0, len(folder_teams), 2):
            rows.append({"kind": "teams", "folder": folder, "teams": folder_teams[index:index + 2]})
    return rows


class LeagueRendererMixin:
    """Calendar, fixture, result and standings screens for league play."""

    def _league_button(
        self,
        rect: pygame.Rect,
        label: str,
        action: str,
        *,
        active: bool = False,
        accent: tuple[int, int, int] = GOLD,
        small: bool = False,
    ) -> None:
        hover = rect.collidepoint(self.logical_mouse_pos())
        color = accent if active or hover else (225, 222, 209)
        pygame.draw.rect(self.screen, color, rect, border_radius=7)
        pygame.draw.rect(self.screen, INK, rect, 2, border_radius=7)
        self.text(label, 10 if small else 12, INK, rect.center, bold=True, center=True)
        self.league_buttons.append((rect, action))

    def draw_league_screen(self) -> None:
        manager = self.league_manager
        self.league_buttons.clear()
        if self.league_save_select_open:
            self._draw_league_save_select()
            return
        self.screen.fill((30, 39, 47))
        pygame.draw.rect(self.screen, (48, 105, 70), (0, 0, WIDTH, 72))
        self.text("KADOCALCIO LEAGUE", 14, GOLD, (24, 13), bold=True)
        self.text("リーグ戦", 30, CREAM, (24, 31), bold=True)
        self.text(manager.date_label, 22, CREAM, (WIDTH - 24, 24), bold=True, right=True)

        sidebar = pygame.Rect(20, 88, 266, 612)
        pygame.draw.rect(self.screen, PAPER, sidebar, border_radius=12)
        pygame.draw.rect(self.screen, GOLD, sidebar, 2, border_radius=12)
        self.text("シミュレーションする大会", 14, INK, (sidebar.left + 16, sidebar.top + 16), bold=True)
        competitions = [("league", name) for name in manager.league_names] + [("tournament", name) for name in manager.tournament_names]
        visible_count = 7
        maximum_scroll = max(0, len(competitions) - visible_count)
        self.league_competition_scroll = min(self.league_competition_scroll, maximum_scroll)
        for index, (kind, competition_name) in enumerate(competitions[self.league_competition_scroll:self.league_competition_scroll + visible_count]):
            rect = pygame.Rect(sidebar.left + 16, sidebar.top + 48 + index * 31, sidebar.width - 45, 25)
            active = competition_name in (manager.selected_leagues if kind == "league" else manager.selected_tournaments)
            mark = "✓" if active else "　"
            team_count = len(manager.teams_in_league(competition_name)) if kind == "league" else len(manager._tournament_participants(manager.tournament_definition(competition_name)))
            color = manager.league_color(competition_name) if kind == "league" else (216, 124, 63)
            self._league_button(
                rect,
                f"{mark} {'L' if kind == 'league' else 'T'} {competition_name}　{team_count}",
                f"toggle|{competition_name}" if kind == "league" else f"toggle_tournament|{competition_name}",
                active=active,
                accent=color, small=True,
            )
        if maximum_scroll:
            track = pygame.Rect(sidebar.right - 22, sidebar.top + 48, 8, 211)
            pygame.draw.rect(self.screen, (205, 201, 187), track, border_radius=4)
            thumb_h = max(24, round(track.height * visible_count / len(competitions)))
            thumb_y = track.top + round((track.height - thumb_h) * self.league_competition_scroll / maximum_scroll)
            pygame.draw.rect(self.screen, GOLD, (track.left, thumb_y, track.width, thumb_h), border_radius=4)
            if thumb_y > track.top:
                self.league_buttons.append((pygame.Rect(track.left - 5, track.top, track.width + 10, thumb_y - track.top), "competition_scroll|-7"))
            thumb_bottom = thumb_y + thumb_h
            if thumb_bottom < track.bottom:
                self.league_buttons.append((pygame.Rect(track.left - 5, thumb_bottom, track.width + 10, track.bottom - thumb_bottom), "competition_scroll|7"))

        self.text("日付をクリックして進行", 12, MUTED, (sidebar.centerx, sidebar.top + 278), center=True)
        self._league_button(
            pygame.Rect(sidebar.left + 16, sidebar.top + 304, sidebar.width - 32, 44),
            "1日進める",
            "advance_day",
            accent=(91, 180, 111),
        )
        next_day = manager.next_matchday()
        next_label = f"次の試合までスキップ（{next_day}日目）" if next_day is not None else "次の試合日なし"
        self._league_button(
            pygame.Rect(sidebar.left + 16, sidebar.top + 358, sidebar.width - 32, 44),
            next_label,
            "advance_matchday",
            accent=(91, 180, 111),
            small=True,
        )
        if manager.watch_fixture_id:
            fixture = manager.fixture(manager.watch_fixture_id)
            if fixture:
                self.text("観戦予約", 11, HOME_RED, (sidebar.left + 16, sidebar.top + 426), bold=True)
                self.text(
                    f"{fixture['day']}日目 {fixture['home_name']} vs {fixture['away_name']}",
                    10, INK, (sidebar.left + 16, sidebar.top + 449),
                )
        self._league_button(
            pygame.Rect(sidebar.left + 16, sidebar.bottom - 98, sidebar.width - 32, 34),
            "途中保存",
            "save_current",
            accent=(91, 180, 111),
        )
        self._league_button(
            pygame.Rect(sidebar.left + 16, sidebar.bottom - 56, sidebar.width - 32, 34),
            "保存してセーブ選択へ",
            "manage_saves",
        )

        main = pygame.Rect(304, 88, 956, 612)
        pygame.draw.rect(self.screen, PAPER, main, border_radius=12)
        pygame.draw.rect(self.screen, GOLD, main, 2, border_radius=12)
        # Keep competition navigation in a fixed-width area. A row of one tab
        # per league eventually collided with the screen tabs as leagues grew.
        league_names = manager.league_names
        if self.league_view_name not in league_names and league_names:
            self.league_view_name = league_names[0]
        league_index = league_names.index(self.league_view_name) if self.league_view_name in league_names else 0
        selector_y = main.top + 14
        self._league_button(pygame.Rect(main.left + 18, selector_y, 34, 32), "◀", "league_cycle|-1", small=True)
        current_rect = pygame.Rect(main.left + 60, selector_y, 330, 32)
        current_color = manager.league_color(self.league_view_name) if self.league_view_name in league_names else GOLD
        pygame.draw.rect(self.screen, (239, 236, 222), current_rect, border_radius=7)
        pygame.draw.rect(self.screen, current_color, current_rect, 2, border_radius=7)
        current_label = f"{league_index + 1} / {len(league_names)}　{self.league_view_name}" if league_names else "リーグなし"
        self.text(current_label, 12, INK, current_rect.center, bold=True, center=True)
        self._league_button(pygame.Rect(main.left + 398, selector_y, 34, 32), "▶", "league_cycle|1", small=True)
        self._league_button(
            pygame.Rect(main.right - 350, main.top + 14, 96, 32),
            "成績", "tab|standings", active=self.league_tab == "standings",
        )
        self._league_button(
            pygame.Rect(main.right - 246, main.top + 14, 104, 32),
            "日程・観戦", "tab|schedule", active=self.league_tab == "schedule", small=True,
        )
        self._league_button(
            pygame.Rect(main.right - 134, main.top + 14, 116, 32),
            "リーグ戦編集", "tab|structure", active=self.league_tab == "structure", small=True,
        )

        if self.league_tab == "schedule":
            self._draw_league_schedule(main)
        elif self.league_tab == "structure":
            self._draw_league_structure(main)
        else:
            self._draw_league_standings(main)
        session = self.league_simulation_session
        if session is not None:
            shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            shade.fill((19, 24, 31, 188))
            self.screen.blit(shade, (0, 0))
            panel = pygame.Rect(WIDTH // 2 - 270, HEIGHT // 2 - 96, 540, 192)
            pygame.draw.rect(self.screen, PAPER, panel, border_radius=14)
            pygame.draw.rect(self.screen, GOLD, panel, 4, border_radius=14)
            self.text("リーグ戦を実試合シミュレーション中", 20, INK, (panel.centerx, panel.top + 42), bold=True, center=True)
            self.text(
                f"通常と同じ選手AI・ボール・反則処理　{session.completed}/{session.total}試合完了",
                12, MUTED, (panel.centerx, panel.top + 82), center=True,
            )
            bar = pygame.Rect(panel.left + 54, panel.top + 116, panel.width - 108, 22)
            pygame.draw.rect(self.screen, (207, 204, 192), bar, border_radius=7)
            fill = pygame.Rect(bar.left, bar.top, round(bar.width * session.progress), bar.height)
            pygame.draw.rect(self.screen, (66, 154, 91), fill, border_radius=7)
            self.text(
            f"自動設定：同時{session.worker_count}試合 / 全{session.total}試合 / 約{session.estimated_waves}巡　"
            f"論理{session.detected_cpu_count}CPU・空きメモリ{session.available_memory_gb:.1f}GBを考慮",
                10, MUTED, (panel.centerx, panel.bottom - 25), center=True,
            )

    def _draw_league_save_select(self) -> None:
        manager = self.league_manager
        self.screen.fill((30, 39, 47))
        pygame.draw.rect(self.screen, (48, 105, 70), (0, 0, WIDTH, 72))
        self.text("KADOCALCIO LEAGUE", 14, GOLD, (24, 13), bold=True)
        self.text("リーグ戦セーブデータ", 29, CREAM, (24, 31), bold=True)
        panel = pygame.Rect(70, 94, WIDTH - 140, HEIGHT - 132)
        pygame.draw.rect(self.screen, PAPER, panel, border_radius=14)
        pygame.draw.rect(self.screen, GOLD, panel, 3, border_radius=14)

        self.text("新しいリーグ戦", 18, INK, (panel.left + 26, panel.top + 20), bold=True)
        input_rect = pygame.Rect(panel.left + 26, panel.top + 54, 420, 40)
        pygame.draw.rect(self.screen, (255, 253, 242), input_rect, border_radius=7)
        pygame.draw.rect(self.screen, GOLD if self.league_save_input_active else (176, 174, 165), input_rect, 2, border_radius=7)
        input_text = (self.league_new_save_name + self.ime_composition) if self.league_save_input_active else self.league_new_save_name
        input_text = input_text or "セーブ名を入力"
        self.text(input_text, 14, INK if self.league_new_save_name else MUTED, (input_rect.left + 12, input_rect.top + 10))
        self.league_buttons.append((input_rect, "save_input"))
        self._league_button(pygame.Rect(input_rect.right + 14, input_rect.top, 154, input_rect.height), "新規開始", "new_save", accent=(91, 180, 111))
        self._league_button(pygame.Rect(panel.right - 174, input_rect.top, 144, input_rect.height), "チーム選択へ戻る", "save_back", small=True)

        pygame.draw.line(self.screen, (190, 187, 176), (panel.left + 24, panel.top + 116), (panel.right - 24, panel.top + 116), 2)
        self.text("保存済みリーグ戦（league_save/*.json）", 16, INK, (panel.left + 26, panel.top + 132), bold=True)
        saves = manager.list_saves()
        if not saves:
            self.text("セーブデータはまだありません", 14, MUTED, (panel.left + 28, panel.top + 174))
        for index, info in enumerate(saves[:6]):
            row = pygame.Rect(panel.left + 24, panel.top + 166 + index * 62, panel.width - 48, 54)
            has_error = bool(info["errors"])
            pygame.draw.rect(self.screen, (250, 226, 220) if has_error else (236, 233, 220), row, border_radius=7)
            pygame.draw.rect(self.screen, HOME_RED if has_error else (195, 191, 177), row, 2, border_radius=7)
            self.text(str(info["name"]), 14, INK, (row.left + 12, row.top + 7), bold=True)
            detail = f"year{info['year']}  {info['day']}日目"
            if info.get("saved_at"):
                detail += f"　保存 {str(info['saved_at']).replace('T', ' ')}"
            self.text(detail, 10, MUTED, (row.left + 12, row.top + 31))
            if has_error:
                extra = f"（ほか{len(info['errors']) - 1}件）" if len(info["errors"]) > 1 else ""
                self.text("エラー: " + str(info["errors"][0])[:48] + extra, 10, HOME_RED, (row.left + 360, row.top + 9), bold=True)
            else:
                self._league_button(pygame.Rect(row.right - 244, row.top + 9, 108, 36), "途中から再開", f"resume|{info['file_name']}", accent=(91, 180, 111), small=True)
            deleting = self.league_delete_confirm == info["file_name"]
            self._league_button(
                pygame.Rect(row.right - 124, row.top + 9, 108, 36),
                "削除する" if deleting else "削除",
                f"delete|{info['file_name']}", active=deleting, accent=HOME_RED, small=True,
            )
        if self.league_save_message:
            color = HOME_RED if ("エラー" in self.league_save_message or "見つかりません" in self.league_save_message) else (48, 105, 70)
            self.text(self.league_save_message[:100], 11, color, (panel.left + 26, panel.bottom - 26), bold=True)

    def _draw_league_standings(self, main: pygame.Rect) -> None:
        manager = self.league_manager
        league_name = self.league_view_name
        years = manager.available_years()
        if self.league_history_year not in years:
            self.league_history_year = manager.year
        year = self.league_history_year
        table = manager.standings_for_year(league_name, year)
        title_suffix = "途中成績" if year == manager.year else "最終成績"
        self.text(f"{league_name}  year{year} {title_suffix}", 21, INK, (main.left + 24, main.top + 67), bold=True)
        current_index = years.index(year)
        if current_index < len(years) - 1:
            older = years[current_index + 1]
            self._league_button(pygame.Rect(main.right - 236, main.top + 64, 98, 30), f"← year{older}", f"history|{older}", small=True)
        if current_index > 0:
            newer = years[current_index - 1]
            self._league_button(pygame.Rect(main.right - 128, main.top + 64, 98, 30), f"year{newer} →", f"history|{newer}", small=True)
        header_y = main.top + 108
        columns = (
            ("順位", main.left + 28), ("チーム", main.left + 88), ("試", main.left + 520),
            ("勝", main.left + 574), ("分", main.left + 624), ("敗", main.left + 674),
            ("得", main.left + 728), ("失", main.left + 780), ("差", main.left + 834),
            ("勝点", main.left + 894),
        )
        pygame.draw.rect(self.screen, (45, 54, 62), (main.left + 18, header_y - 8, main.width - 36, 34), border_radius=5)
        for label, x in columns:
            self.text(label, 11, CREAM, (x, header_y), bold=True)
        if not table:
            self.text("所属チームが2チーム以上になると日程と成績が作成されます", 16, MUTED, main.center, center=True)
            return
        for index, row in enumerate(table[:16], start=1):
            y = header_y + 35 + (index - 1) * 30
            if index % 2:
                pygame.draw.rect(self.screen, (234, 231, 218), (main.left + 18, y - 7, main.width - 36, 27))
            self.text(str(index), 12, INK, (main.left + 39, y), bold=True, center=True)
            self.text(str(row["name"]), 12, INK, (main.left + 88, y), bold=index <= 3)
            values = (row["played"], row["won"], row["drawn"], row["lost"], row["gf"], row["ga"], row["gd"], row["points"])
            xs = (main.left + 530, main.left + 582, main.left + 632, main.left + 682, main.left + 736, main.left + 788, main.left + 842, main.left + 914)
            for value, x in zip(values, xs):
                self.text(str(value), 12, HOME_RED if x == xs[-1] else INK, (x, y), bold=x == xs[-1], center=True)
        events = [
            event for event in manager.promotion_events_for_year(year)
            if league_name in (event.get("upper_league"), event.get("lower_league"))
        ]
        if events:
            promoted = [event for event in events if event.get("promoted")]
            summary = "　".join(
                f"↑{event['lower_team_name']} / ↓{event['upper_team_name']}" for event in promoted[:2]
            ) or "入れ替えなし"
            self.text(f"入れ替え戦結果：{summary}", 11, HOME_RED, (main.left + 24, main.bottom - 44), bold=True)
        self.text("順位：勝点 → 得失点差 → 総得点 → 勝利数", 11, MUTED, (main.left + 24, main.bottom - 24))

    def _draw_league_schedule(self, main: pygame.Rect) -> None:
        manager = self.league_manager
        fixtures = manager.next_fixtures()
        next_day = manager.next_matchday()
        title = f"次の試合日　{next_day}日目" if next_day is not None else "今季の日程は終了しました"
        self.text(title, 20, INK, (main.left + 24, main.top + 67), bold=True)
        self.text("観戦を予約しなければ、日付到達時に結果だけを自動計算します", 11, MUTED, (main.left + 24, main.top + 96))
        for index, fixture in enumerate(fixtures[:8]):
            y = main.top + 126 + index * 42
            rect = pygame.Rect(main.left + 20, y, main.width - 40, 34)
            pygame.draw.rect(self.screen, (235, 232, 219) if index % 2 == 0 else (227, 225, 214), rect, border_radius=5)
            fixture_label = fixture.get("competition_label") or f"{fixture['league']} 第{fixture['round']}節"
            self.text(str(fixture_label), 10, MUTED, (rect.left + 10, rect.centery - 7))
            self.text(f"{fixture['home_name']}　vs　{fixture['away_name']}", 12, INK, (rect.left + 178, rect.centery), bold=True, center=True)
            watch_rect = pygame.Rect(rect.right - 118, rect.top + 4, 108, 26)
            reserved = manager.watch_fixture_id == fixture["id"]
            self._league_button(
                watch_rect,
                "観戦予約中" if reserved else "この試合を観戦",
                f"watch|{fixture['id']}",
                active=reserved,
                accent=HOME_RED,
                small=True,
            )

        result_top = main.top + 478
        pygame.draw.line(self.screen, (190, 187, 176), (main.left + 20, result_top - 12), (main.right - 20, result_top - 12), 2)
        self.text(f"直近の同日結果　{manager.date_label}", 14, INK, (main.left + 24, result_top), bold=True)
        if not manager.last_results:
            self.text("この日の結果はまだありません", 11, MUTED, (main.left + 24, result_top + 28))
        for index, result in enumerate(manager.last_results[:4]):
            y = result_top + 28 + index * 24
            watched = "●" if result.get("watched") else " "
            score = f"{result['home_score']} - {result['away_score']}"
            if result.get("home_penalties") is not None:
                score += f" (PK {result['home_penalties']}-{result['away_penalties']})"
            self.text(f"{watched} {result['league']}  {result['home_name']}", 10, INK, (main.left + 24, y))
            self.text(score, 11, HOME_RED, (main.left + 610, y), bold=True, center=True)
            self.text(str(result["away_name"]), 10, INK, (main.left + 670, y))

    def _draw_league_structure(self, main: pygame.Rect) -> None:
        manager = self.league_manager
        self._league_button(pygame.Rect(main.left + 22, main.top + 57, 112, 36), "リーグ編集", "structure_kind|league", active=self.league_structure_kind == "league", small=True)
        self._league_button(pygame.Rect(main.left + 140, main.top + 57, 132, 36), "トーナメント編集", "structure_kind|tournament", active=self.league_structure_kind == "tournament", small=True)
        if self.league_structure_kind == "tournament":
            self._draw_tournament_structure(main)
            return
        league_name = self.league_view_name
        if league_name not in manager.league_names:
            league_name = manager.league_names[0]
            self.league_view_name = league_name
        name_rect = pygame.Rect(main.left + 286, main.top + 58, 210, 36)
        pygame.draw.rect(self.screen, (255, 253, 242), name_rect, border_radius=6)
        pygame.draw.rect(self.screen, GOLD if self.league_editor_input_active else (188, 185, 173), name_rect, 2, border_radius=6)
        input_name = self.league_editor_name + self.ime_composition if self.league_editor_input_active else self.league_editor_name
        self.text(input_name or "リーグ名", 13, INK, (name_rect.left + 10, name_rect.top + 9), bold=True)
        self.league_buttons.append((name_rect, "editor_name_input"))
        self._league_button(pygame.Rect(name_rect.right + 8, name_rect.top, 82, 36), "名前変更", "editor_rename", small=True)
        self._league_button(pygame.Rect(name_rect.right + 98, name_rect.top, 82, 36), "新規追加", "editor_add", accent=(91, 180, 111), small=True)
        deleting = self.league_editor_delete_confirm == league_name
        self._league_button(
            pygame.Rect(name_rect.right + 188, name_rect.top, 82, 36),
            "削除する" if deleting else "削除", "editor_delete",
            active=deleting, accent=HOME_RED, small=True,
        )

        mode_y = main.top + 106
        self._league_button(pygame.Rect(main.left + 22, mode_y, 126, 32), "チーム配置", "editor_mode|teams", active=self.league_editor_mode == "teams", small=True)
        self._league_button(pygame.Rect(main.left + 156, mode_y, 126, 32), "試合日程編集", "editor_mode|schedule", active=self.league_editor_mode == "schedule", small=True)
        self.text("上位リーグ", 10, MUTED, (main.left + 326, mode_y + 10), bold=True)
        upper = manager.upper_league(league_name) or "なし（最上位）"
        upper_value = pygame.Rect(main.left + 444, mode_y, 220, 32)
        pygame.draw.rect(self.screen, (255, 253, 242), upper_value, border_radius=5)
        pygame.draw.rect(self.screen, (188, 185, 173), upper_value, 2, border_radius=5)
        self.text(upper, 11, INK, upper_value.center, bold=True, center=True)
        self._league_button(pygame.Rect(upper_value.left - 36, mode_y, 30, 32), "◀", f"upper|{league_name}|-1", small=True)
        self._league_button(pygame.Rect(upper_value.right + 6, mode_y, 30, 32), "▶", f"upper|{league_name}|1", small=True)

        if self.league_editor_mode == "schedule":
            self._draw_league_schedule_editor(main, league_name)
        else:
            self._draw_league_team_editor(main, league_name)
        if self.league_save_message:
            color = HOME_RED if any(word in self.league_save_message for word in ("できません", "見つかりません", "空です", "必要です")) else (48, 105, 70)
            self.text(self.league_save_message[:100], 10, color, (main.left + 24, main.bottom - 22), bold=True)

    def _draw_tournament_structure(self, main: pygame.Rect) -> None:
        manager = self.league_manager
        names = manager.tournament_names
        if self.tournament_view_name not in names:
            self.tournament_view_name = names[0] if names else ""
        name_rect = pygame.Rect(main.left + 286, main.top + 58, 210, 36)
        pygame.draw.rect(self.screen, (255, 253, 242), name_rect, border_radius=6)
        pygame.draw.rect(self.screen, GOLD if self.league_editor_input_active else (188, 185, 173), name_rect, 2, border_radius=6)
        display_name = self.league_editor_name + self.ime_composition if self.league_editor_input_active else self.league_editor_name
        self.text(display_name or "トーナメント名", 12, INK, (name_rect.left + 9, name_rect.top + 10), bold=True)
        self.league_buttons.append((name_rect, "editor_name_input"))
        self._league_button(pygame.Rect(name_rect.right + 8, name_rect.top, 76, 36), "名前変更", "tournament_rename", small=True)
        self._league_button(pygame.Rect(name_rect.right + 90, name_rect.top, 76, 36), "新規追加", "tournament_add", accent=(91, 180, 111), small=True)
        self._league_button(pygame.Rect(name_rect.right + 172, name_rect.top, 76, 36), "削除", "tournament_delete", accent=HOME_RED, small=True)

        if not names:
            self.text("名前を入力して『新規追加』を押すとトーナメントを作成できます", 16, MUTED, main.center, center=True)
            if self.league_save_message:
                self.text(self.league_save_message[:100], 11, HOME_RED, (main.centerx, main.centery + 42), bold=True, center=True)
            return
        self.text(f"作成済みトーナメント　{names.index(self.tournament_view_name) + 1}/{len(names)}", 11, MUTED, (main.left + 24, main.top + 120), bold=True)
        self._league_button(pygame.Rect(main.left + 24, main.top + 143, 38, 32), "◀", "tournament_cycle|-1", small=True)
        current_rect = pygame.Rect(main.left + 72, main.top + 143, 360, 32)
        pygame.draw.rect(self.screen, (236, 233, 220), current_rect, border_radius=6)
        pygame.draw.rect(self.screen, (216, 124, 63), current_rect, 2, border_radius=6)
        self.text(self.tournament_view_name, 13, INK, current_rect.center, bold=True, center=True)
        self._league_button(pygame.Rect(main.left + 442, main.top + 143, 38, 32), "▶", "tournament_cycle|1", small=True)
        definition = manager.tournament_definition(self.tournament_view_name)
        y = main.top + 195
        self.text("参加元リーグ（複数選択）", 12, INK, (main.left + 30, y + 9), bold=True)
        sources = set(definition.get("対象リーグ一覧") or [definition.get("対象リーグ", "")])
        maximum_source_scroll = max(0, len(manager.league_names) - 6)
        self.tournament_source_scroll = min(self.tournament_source_scroll, maximum_source_scroll)
        shown_sources = manager.league_names[self.tournament_source_scroll:self.tournament_source_scroll + 6]
        for index, league_name in enumerate(shown_sources):
            rect = pygame.Rect(main.left + 190 + (index % 3) * 180, y + (index // 3) * 36, 168, 30)
            selected = league_name in sources
            self._league_button(rect, ("✓ " if selected else "　") + league_name, f"tournament_source_toggle|{league_name}", active=selected, accent=manager.league_color(league_name), small=True)
        if maximum_source_scroll:
            self._league_button(pygame.Rect(main.right - 58, y, 30, 30), "▲", "tournament_source_page|-6", small=True)
            self._league_button(pygame.Rect(main.right - 58, y + 36, 30, 30), "▼", "tournament_source_page|6", small=True)
        y += 82
        self.text("参加方式", 12, INK, (main.left + 30, y + 9), bold=True)
        mode = str(definition.get("参加方式", "リーグ全体"))
        self._league_button(pygame.Rect(main.left + 170, y, 210, 34), mode, "tournament_mode", accent=(216, 124, 63), small=True)
        if mode == "前年順位":
            limit = int(definition.get("前年順位上限", 4))
            self.text(f"各リーグ前年 {limit}位まで", 12, INK, (main.left + 485, y + 16), bold=True, center=True)
            self._league_button(pygame.Rect(main.left + 570, y, 34, 32), "−", "tournament_rank|-1", small=True)
            self._league_button(pygame.Rect(main.left + 610, y, 34, 32), "＋", "tournament_rank|1", small=True)
        y += 54
        preferred = int(definition.get("開始希望日", 40))
        self.text("開始希望日（リーグ開催日を自動回避）", 12, INK, (main.left + 30, y + 9), bold=True)
        self.text(f"{preferred}日目", 13, HOME_RED, (main.left + 390, y + 16), bold=True, center=True)
        for amount, label, x in ((-7, "-7", 480), (-1, "-1", 530), (1, "+1", 580), (7, "+7", 630)):
            self._league_button(pygame.Rect(main.left + x, y, 42, 32), label, f"tournament_day|{amount}", small=True)
        participants = manager._tournament_participants(definition)
        self.text(f"現在の参加予定：{len(participants)}チーム　同点はPK戦で決着", 12, MUTED, (main.left + 30, y + 64), bold=True)
        self.text("各ラウンドは前ラウンド後の最短の空き日に進行。year1は現在の配置順を使用します", 11, MUTED, (main.left + 30, y + 90))
        if self.league_save_message:
            color = HOME_RED if any(word in self.league_save_message for word in ("できません", "見つかりません", "空です", "必要です")) else (48, 105, 70)
            self.text(self.league_save_message[:100], 10, color, (main.left + 24, main.bottom - 22), bold=True)

    def _draw_league_team_editor(self, main: pygame.Rect, league_name: str) -> None:
        manager = self.league_manager
        rows = build_team_folder_rows(manager.team_choices)
        viewport = pygame.Rect(main.left + 22, main.top + 176, main.width - 66, main.height - 226)
        self.league_team_scroll_rect = viewport.copy()
        row_height = 44
        visible_count = max(1, viewport.height // row_height)
        maximum_scroll = max(0, len(rows) - visible_count)
        self.league_team_scroll = max(0, min(self.league_team_scroll, maximum_scroll))
        visible_rows = rows[self.league_team_scroll:self.league_team_scroll + visible_count]
        current_folder = visible_rows[0]["folder"] if visible_rows else "チームなし"
        self.text(
            f"フォルダ別一覧をスクロールして配置・解除　表示中：{current_folder}",
            10, MUTED, (main.left + 24, main.top + 151),
        )
        for visible_index, display_row in enumerate(visible_rows):
            y = viewport.top + visible_index * row_height
            if display_row["kind"] == "folder":
                folder_teams = display_row["teams"]
                selected_count = sum(
                    manager.team_in_league(str(team.get("id", "")), league_name)
                    for team in folder_teams
                )
                header = pygame.Rect(viewport.left, y + 4, viewport.width, 34)
                pygame.draw.rect(self.screen, (214, 219, 210), header, border_radius=6)
                pygame.draw.rect(self.screen, (154, 159, 151), header, 1, border_radius=6)
                self.text(f"フォルダ　{display_row['folder']}", 11, INK, (header.left + 12, header.top + 9), bold=True)
                self.text(
                    f"{selected_count}/{len(folder_teams)}チーム配置",
                    10, MUTED, (header.right - 12, header.top + 10), bold=True, right=True,
                )
                continue
            column_width = (viewport.width - 12) // 2
            for column, team in enumerate(display_row["teams"]):
                row = pygame.Rect(viewport.left + column * (column_width + 12), y + 3, column_width, 38)
                self._draw_league_team_row(row, team, league_name)

        if maximum_scroll:
            track = pygame.Rect(viewport.right + 10, viewport.top, 12, viewport.height)
            pygame.draw.rect(self.screen, (205, 202, 190), track, border_radius=6)
            thumb_height = max(34, round(track.height * visible_count / len(rows)))
            thumb_y = track.top + round((track.height - thumb_height) * self.league_team_scroll / maximum_scroll)
            thumb = pygame.Rect(track.left, thumb_y, track.width, thumb_height)
            pygame.draw.rect(self.screen, GOLD, thumb, border_radius=6)
            if thumb.top > track.top:
                self.league_buttons.append((pygame.Rect(track.left - 5, track.top, track.width + 10, thumb.top - track.top), f"team_scroll|-{visible_count}"))
            if thumb.bottom < track.bottom:
                self.league_buttons.append((pygame.Rect(track.left - 5, thumb.bottom, track.width + 10, track.bottom - thumb.bottom), f"team_scroll|{visible_count}"))
            self.text(
                f"{self.league_team_scroll + 1}–{min(len(rows), self.league_team_scroll + visible_count)} / {len(rows)}",
                9, MUTED, (track.right, viewport.bottom + 5), right=True,
            )

    def _draw_league_team_row(self, row: pygame.Rect, team: dict, league_name: str) -> None:
        manager = self.league_manager
        team_id = str(team.get("id", ""))
        priority = manager.league_memberships.get(team_id, "")
        participations = manager.league_participations.get(team_id, [])
        selected = manager.team_in_league(team_id, league_name)
        pygame.draw.rect(self.screen, (226, 239, 220) if selected else (236, 233, 220), row, border_radius=6)
        pygame.draw.rect(self.screen, manager.league_color(league_name) if selected else (197, 193, 180), row, 2, border_radius=6)
        button_width = 58
        priority_width = 54 if selected and priority != league_name else 0
        text_right = row.right - button_width - priority_width - 20
        name = str(team.get("name", team_id))
        while len(name) > 4 and self.font(10, True).size(name)[0] > text_right - row.left - 10:
            name = name[:-2] + "…"
        self.text(name, 10, INK, (row.left + 9, row.top + 5), bold=selected)
        current_label = " / ".join(("★" if name == priority else "") + name for name in participations) or "未所属"
        if len(current_label) > 23:
            current_label = current_label[:22] + "…"
        self.text(current_label, 8, MUTED, (row.left + 9, row.top + 23))
        button_label = "外す" if selected else "追加"
        self._league_button(
            pygame.Rect(row.right - button_width - 7, row.top + 5, button_width, 28), button_label,
            f"assign_team|{team_id}", active=selected,
            accent=manager.league_color(league_name), small=True,
        )
        if selected and priority != league_name:
            self._league_button(
                pygame.Rect(row.right - button_width - priority_width - 11, row.top + 5, priority_width, 28), "優先",
                f"priority_team|{team_id}", accent=GOLD, small=True,
            )

    def _draw_league_schedule_editor(self, main: pygame.Rect, league_name: str) -> None:
        manager = self.league_manager
        fixtures = sorted(
            [fixture for fixture in manager.fixtures if fixture.get("league") == league_name and fixture.get("fixture_type", "REGULAR") == "REGULAR"],
            key=lambda fixture: (int(fixture.get("day", 0)), int(fixture.get("round", 0)), str(fixture.get("home_name", ""))),
        )
        per_page = 8
        max_page = max(0, (len(fixtures) - 1) // per_page)
        self.league_editor_schedule_page = min(self.league_editor_schedule_page, max_page)
        start = self.league_editor_schedule_page * per_page
        self.text("自動生成後の未消化試合日を変更できます（入れ替え戦は固定）", 10, MUTED, (main.left + 24, main.top + 151))
        if not fixtures:
            self.text("2チーム以上配置するとホーム＆アウェーの日程が自動生成されます", 15, MUTED, (main.centerx, main.centery), center=True)
            return
        for index, fixture in enumerate(fixtures[start:start + per_page]):
            row = pygame.Rect(main.left + 22, main.top + 176 + index * 45, main.width - 44, 38)
            pygame.draw.rect(self.screen, (236, 233, 220) if index % 2 == 0 else (228, 226, 214), row, border_radius=6)
            self.text(f"第{fixture['round']}節", 10, MUTED, (row.left + 10, row.top + 11), bold=True)
            self.text(f"{fixture['home_name']} vs {fixture['away_name']}", 11, INK, (row.left + 78, row.top + 11), bold=True)
            day_x = row.right - 286
            self.text(f"{fixture['day']}日目", 12, HOME_RED, (day_x, row.centery), bold=True, center=True)
            for offset, label, x in ((-7, "-7", row.right - 218), (-1, "-1", row.right - 166), (1, "+1", row.right - 114), (7, "+7", row.right - 62)):
                self._league_button(pygame.Rect(x, row.top + 5, 44, 28), label, f"fixture_day|{fixture['id']}|{offset}", small=True)
        if max_page:
            self._league_button(pygame.Rect(main.right - 180, main.bottom - 48, 70, 28), "前へ", "schedule_page|-1", small=True)
            self._league_button(pygame.Rect(main.right - 100, main.bottom - 48, 70, 28), "次へ", "schedule_page|1", small=True)
            self.text(f"{self.league_editor_schedule_page + 1}/{max_page + 1}", 10, MUTED, (main.right - 220, main.bottom - 41), right=True)
