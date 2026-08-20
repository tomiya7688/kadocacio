from __future__ import annotations

import pygame


class GpuPresenter:
    """SDL2 GPU presentation with a safe fallback handled by Game.

    Match drawing remains on the logical Pygame surface. Uploading that surface
    as a streaming texture moves final scaling, letterboxing and presentation to
    the GPU without changing the simulation or hit boxes.
    """

    def __init__(
        self,
        title: str,
        window_size: tuple[int, int],
        logical_size: tuple[int, int],
    ) -> None:
        from pygame._sdl2.video import Renderer, Texture, Window

        self.logical_size = logical_size
        self.windowed_size = window_size
        self.fullscreen = False
        self.window = Window(title, size=window_size, resizable=False)
        try:
            self.renderer = Renderer(self.window, accelerated=True, vsync=False)
            self.texture = Texture(self.renderer, logical_size, streaming=True)
        except Exception:
            self.window.destroy()
            raise

    @property
    def size(self) -> tuple[int, int]:
        return tuple(self.window.size)

    def set_window_size(self, size: tuple[int, int]) -> None:
        self.windowed_size = size
        if self.fullscreen:
            self.window.set_windowed()
            self.fullscreen = False
        self.window.size = size

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled == self.fullscreen:
            return
        if enabled:
            self.window.set_fullscreen(True)
        else:
            self.window.set_windowed()
            self.window.size = self.windowed_size
        self.fullscreen = enabled

    def present(self, surface: pygame.Surface) -> None:
        window_width, window_height = self.size
        logical_width, logical_height = self.logical_size
        scale = min(window_width / logical_width, window_height / logical_height)
        render_size = (
            max(1, round(logical_width * scale)),
            max(1, round(logical_height * scale)),
        )
        destination = pygame.Rect(
            (window_width - render_size[0]) // 2,
            (window_height - render_size[1]) // 2,
            *render_size,
        )
        self.texture.update(surface)
        self.renderer.draw_color = (10, 12, 15, 255)
        self.renderer.clear()
        # pygame-ce used ``dstrect`` in some examples, while pygame 2.6.x's
        # compatibility blit exposes the argument as ``dest``.
        self.renderer.blit(self.texture, dest=destination)
        self.renderer.present()

    def destroy(self) -> None:
        self.window.destroy()
