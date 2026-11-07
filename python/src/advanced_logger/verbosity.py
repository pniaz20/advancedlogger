from enum import IntEnum

class Verbosity(IntEnum):
    """Enum class for determining logging verbosity levels in other functions."""
    NOTHING = 0
    MESSAGES = 1
    ALL_MESSAGES = 2
    EVERYTHING = 3