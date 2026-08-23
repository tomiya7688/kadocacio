import random
import unittest

from scripts.app.stadium_system import build_stadium_crowd, roll_special_spectators, stadium_seat_slots


class StadiumGuestTests(unittest.TestCase):
    def test_each_ordinary_spectator_has_a_unique_seat(self) -> None:
        crowd = build_stadium_crowd(random.Random(824), 954)
        seats = [(x, y) for x, y, _ in crowd]
        self.assertEqual(len(seats), len(set(seats)))

    def test_zero_chance_never_adds_a_guest(self) -> None:
        self.assertEqual(roll_special_spectators(random.Random(1), chance=0.0), [])

    def test_full_chance_adds_both_guests_to_different_seats(self) -> None:
        guests = roll_special_spectators(random.Random(1), chance=1.0)
        self.assertEqual({guest[0] for guest in guests}, {"kadoka", "maru"})
        self.assertEqual(len({(guest[1], guest[2]) for guest in guests}), 2)
        valid_seats = set(stadium_seat_slots(954))
        self.assertTrue(all((guest[1], guest[2]) in valid_seats for guest in guests))


if __name__ == "__main__":
    unittest.main()
