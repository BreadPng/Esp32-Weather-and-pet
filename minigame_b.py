"""Placeholder implementation for Mini Game B."""


GAME_NAME = "Mini Game B"


def main_loop(oled, encoder):
    """Run the mini game. Placeholder that immediately exits."""
    try:
        if encoder is not None:
            encoder.reset()
    except AttributeError:
        pass

    return


