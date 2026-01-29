import argparse


class CliSubcommand:
    def __init__(self, name: str, help: str):
        self.name = name
        self.help = help

    def add_to_parser(self, parser: argparse.ArgumentParser):
        subparser = parser.add_parser(self.name, help=self.help)
        subparser.set_defaults(func=self._func)
        self._add_arguments(subparser)

    def _func(args) -> int:
        raise NotImplementedError

    def _add_arguments(self, parser: argparse.ArgumentParser) -> None:
        raise NotImplementedError
