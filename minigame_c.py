"""Placeholder implementation for Mini Game C."""


GAME_NAME = "Mini Game C"


def main_loop(oled, encoder):
    """Run the mini game. Placeholder that immediately exits."""
    try:
        if encoder is not None:
            encoder.reset()
    except AttributeError:
        pass

    return


