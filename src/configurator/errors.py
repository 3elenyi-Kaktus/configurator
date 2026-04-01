class OptionNameOverlap(Exception):
    pass


class InvalidConfig(Exception):
    pass


class InvalidOptionName(Exception):
    pass


class ExclusiveGroupViolation(Exception):
    pass


class DependencyViolation(Exception):
    pass


class MissingOption(Exception):
    pass


class InvalidOptionValue(Exception):
    pass
