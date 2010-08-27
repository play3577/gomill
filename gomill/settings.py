"""Support for describing configurable values."""


def interpret_enum(*values):
    def interpreter(value):
        if value not in values:
            raise ValueError("unknown value")
        return value
    return interpreter

def interpret_int(i):
    if not isinstance(i, int) or isinstance(i, long):
        raise ValueError("invalid integer")
    return i

def interpret_float(f):
    if isinstance(f, float):
        return f
    if isinstance(f, int) or isinstance(f, long):
        return float(f)
    raise ValueError("invalid float")


class Setting(object):
    """Describe a single setting.

    Instantiate with:
      setting name
      interpreter function
      default value (optional)

    """
    def __init__(self, name, interpreter, default=None):
        self.name = name
        self.interpreter = interpreter
        self.default = default

    def interpret(self, value):
        """Validate the value and normalise if necessary.

        Returns the normalised value (usually unchanged).

        Raises ValueError with a description if the value is invalid.

        """
        return self.interpreter(value)

