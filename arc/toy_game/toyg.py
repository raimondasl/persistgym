"""Toy ARC-style game for $0 offline harness tests (written for this repo).

Not an ARC-AGI-3 game. arc-agi loads it from ENVIRONMENTS_DIR in offline mode,
like a downloaded game. ACTION1 moves the player right and reaching column 3
clears a level; ACTION2 loses a life; ACTION3 does nothing. Two levels.
The same game is embedded in arc/patches/0012 (tests/unit/test_offline_game_loop.py).
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite


class Toyg(ARCBaseGame):
    def __init__(self, seed: int = 0) -> None:
        levels = [
            Level(
                sprites=[Sprite([[9]], name="player", x=0, y=0)],
                grid_size=(4, 4),
                name=f"level-{index}",
            )
            for index in range(2)
        ]
        super().__init__(
            game_id="toyg",
            levels=levels,
            camera=Camera(width=4, height=4),
            available_actions=[1, 2, 3],
            seed=seed,
        )

    def step(self) -> None:
        if self.action.id == GameAction.ACTION1:
            player = self.current_level.get_sprites_by_name("player")[0]
            player.move(1, 0)
            if player.x >= 3:
                self.next_level()
        elif self.action.id == GameAction.ACTION2:
            self.lose()
        self.complete_action()
