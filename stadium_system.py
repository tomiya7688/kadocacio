from __future__ import annotations

import random
from pathlib import Path

import pygame


ASSET_DIR = Path(__file__).resolve().parent / "assets"
SPECIAL_SPECTATOR_CHANCE = 0.04
SPECTATOR_COLORS = (
    (222, 68, 66),
    (66, 132, 213),
    (246, 190, 49),
    (255, 250, 232),
    (76, 87, 102),
)


def _load_image(name: str, *, alpha: bool) -> pygame.Surface | None:
    try:
        image = pygame.image.load(str(ASSET_DIR / name))
    except (FileNotFoundError, pygame.error):
        # A copied build remains playable if an optional visual asset is absent.
        return None
    try:
        return image.convert_alpha() if alpha else image.convert()
    except pygame.error:
        # SDL2's accelerated presenter does not always create a display Surface,
        # but blitting the loaded PNG Surface is still supported.
        return image


def load_stadium_seats(width: int, height: int = 170) -> pygame.Surface | None:
    """Load a wide strip of the generated grandstand without smoothing pixels."""
    image = _load_image("stadium_seats_pixel.png", alpha=False)
    if image is None:
        return None
    source = image.get_rect()
    crop_y = int(source.height * 0.23)
    crop_h = max(1, int(source.height * 0.43))
    seat_band = image.subsurface((0, crop_y, source.width, crop_h)).copy()
    return pygame.transform.scale(seat_band, (width, height))


def load_special_spectator_sprites() -> dict[str, pygame.Surface]:
    sprites: dict[str, pygame.Surface] = {}
    names = {
        "kadoka": "kadoka_supporter_hachimaki.png",
        "maru": "maru_supporter_hachimaki.png",
    }
    for key, filename in names.items():
        image = _load_image(filename, alpha=True)
        if image is None:
            continue
        bounds = image.get_bounding_rect(min_alpha=8)
        if bounds.width > 0 and bounds.height > 0:
            sprites[key] = image.subsurface(bounds).copy()
    return sprites


def stadium_seat_slots(width: int) -> list[tuple[int, int]]:
    """Return the one-person seat grid used by every spectator type."""
    slots: list[tuple[int, int]] = []
    for row, y in enumerate(range(91, 212, 12)):
        first_x = 8 if row % 2 == 0 else 16
        slots.extend((x, y) for x in range(first_x, width - 7, 16))
    return slots


def build_stadium_crowd(
    rng: random.Random,
    width: int,
    *,
    count: int = 360,
) -> list[tuple[int, int, tuple[int, int, int]]]:
    """Fill unique seats; sampling without replacement forbids double seating."""
    slots = stadium_seat_slots(width)
    occupied = rng.sample(slots, min(max(0, count), len(slots)))
    return [(x, y, rng.choice(SPECTATOR_COLORS)) for x, y in occupied]


def roll_special_spectators(
    rng: random.Random,
    *,
    chance: float = SPECIAL_SPECTATOR_CHANCE,
) -> list[tuple[str, int, int, int]]:
    """Choose rare guests once per match, not once per rendered frame."""
    # These positions are members of stadium_seat_slots(954).  Rendering skips
    # an ordinary spectator in the selected seat, so even a guest never shares.
    slots = [(144, 175, 25), (312, 139, 22), (520, 187, 28), (752, 151, 23), (864, 199, 29)]
    rng.shuffle(slots)
    result: list[tuple[str, int, int, int]] = []
    for kind in ("kadoka", "maru"):
        if rng.random() < chance:
            x, y, size = slots.pop()
            result.append((kind, x, y, size))
    return result
