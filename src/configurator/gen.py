from argparse import ArgumentParser
from dataclasses import dataclass
import hashlib
from importlib import util
import inspect
from inspect import Signature, signature
import logging
import os
from pathlib import Path
import re
from re import Pattern
import sys

import black
import isort

from configurator._version import __version__
from configurator.config import IConfig
from configurator.option import Option
from configurator.option_group import OptionGroup


def tabulate(line: str, indent: int) -> str:
    return " " * 4 * indent + line


@dataclass
class OptionInfo:
    name: str
    group_name: str
    config_name: str
    config_type: type
    runtime_type: type


class Generator:
    def __init__(self, module_name: str, object_name: str, output: Path) -> None:
        self.module_name: str = module_name
        self.object_name: str = object_name
        self.output: Path = output

        self.imports: set[tuple[str, str]] = set()
        self.imported_type_pattern: Pattern = re.compile(r"(?P<import_source>[\w.]+)\.(?P<object>\w+)")

        self.option_infos: list[OptionInfo] = []

    def simplifyType(self, input_type: type) -> str:
        logging.info(f"Generator: Simplifying type '{input_type}'")
        type_string: str
        if hasattr(input_type, "__origin__"):
            type_string = str(input_type)
        else:
            type_string = input_type.__name__
        logging.info(f"Generator: Retrieved type '{type_string}'")

        if "." in type_string:
            matches: list[tuple[str, str]] = self.imported_type_pattern.findall(type_string)
            for match in matches:
                logging.info(f"Generator: Adding '{match[0]}.{match[1]}' to type imports")
                self.imports.add(match)
            type_string = self.imported_type_pattern.sub(r"\2", type_string)
            logging.info(f"Generator: Simplified to '{type_string}'")
        return type_string

    def createProperty(self, option_info: OptionInfo) -> list[str]:
        config_type_string: str = self.simplifyType(option_info.config_type)
        runtime_type_string: str = self.simplifyType(option_info.runtime_type)
        res = [
            f"@property\n",
            f"def {option_info.name}(self) -> {runtime_type_string}:\n",
            f"    return self._getOptionValue({option_info.group_name}.{option_info.config_name})\n" f"\n",
            f"@{option_info.name}.setter\n",
            f"def {option_info.name}(self, value: {config_type_string}) -> None:\n",
            f"    self._setOptionValue({option_info.group_name}, {option_info.group_name}.{option_info.config_name}, value)\n",
        ]
        return res

    def collectOptionInfos(self, option_groups: list[type[OptionGroup]]) -> None:
        for option_group in option_groups:
            option_group_name = option_group.__name__
            logging.info(f"Generator: Loading options from group '{option_group_name}'")
            for option_name in option_group.getOptionAttrs():
                option = getattr(option_group, option_name)
                logging.info(f"Generator: Adding option: {option}")
                in_type: type = option.config_inner_type
                out_type: type = option.config_inner_type
                if option.validator is not Option.validator:
                    sign = signature(option.validator)
                    logging.info(f"Generator: Retrieved validator function return type: {sign.return_annotation}")
                    if sign.return_annotation is not Signature.empty:
                        out_type = sign.return_annotation
                self.option_infos.append(OptionInfo(option.name, option_group_name, option_name, in_type, out_type))

    def generate(self) -> None:
        # Load specified user module
        logging.info(f"Generator: Loading module '{self.module_name}' with target object: {self.object_name}")
        spec = util.find_spec(self.module_name)
        logging.info(f"Generator: Loaded spec: {spec}")
        if spec is None:
            raise RuntimeError(f"Module '{self.module_name}' not found")
        user_module = util.module_from_spec(spec)
        sys.modules[self.module_name] = user_module
        spec.loader.exec_module(user_module)

        # Retrieve the list of option groups
        option_groups: list[type[OptionGroup]] = getattr(user_module, self.object_name)
        if (
            not isinstance(option_groups, list)
            or not all(isinstance(x, type) for x in option_groups)
            or not all(issubclass(x, OptionGroup) for x in option_groups)
        ):
            raise RuntimeError(
                f"Invalid option group listing: {option_groups} (expected 'list[type[OptionGroup]]', got: '{type(option_groups)}')"
            )
        self.collectOptionInfos(option_groups)
        properties: list[str] = [
            "".join(tabulate(line, 1) for line in self.createProperty(option_info)) for option_info in self.option_infos
        ]

        logging.info(f"Generator: Creating __init__ signature for ConfigProxy")
        init_params: str = str(inspect.signature(IConfig.__init__))
        matches: list[tuple[str, str]] = self.imported_type_pattern.findall(init_params)
        for match in matches:
            logging.info(f"Generator: Adding '{match[0]}.{match[1]}' to type imports")
            self.imports.add(match)
        init_params = self.imported_type_pattern.sub(r"\2", init_params)
        logging.info(f"Generator: Simplified to '{init_params}'")

        combined_hash: str = IConfig.getOptionGroupsHash(option_groups)

        header_comment: str = (
            f"# ----\n"
            f"# Automatically generated by configurator lib (v{__version__})\n"
            f"# Module used: {self.module_name}:{self.object_name}\n"
            f"# Option groups hash signature:\n"
            f'_option_groups_hash: str = "{combined_hash}"\n'
            f"# ----\n\n"
        )

        type_imports: str = "\n".join(f"from {x[0]} import {x[1]}" for x in self.imports)
        system_imports: str = f"from configurator.config import IConfig\n" f"import logging\n"
        option_groups_imports: str = (
            f"from {self.module_name} import {', '.join(option_group.__name__ for option_group in option_groups)}\n"
        )

        result: str = header_comment
        result += "\n".join([type_imports, system_imports, option_groups_imports])
        result += f"\n" f"\n" f"class ConfigProxy({IConfig.__name__}):\n"
        result += tabulate(f"def __init__{init_params} -> None:\n", 1)
        parameter_names: str = ",".join(x for x in signature(IConfig.__init__).parameters)
        result += tabulate(f"if _option_groups_hash != IConfig.getOptionGroupsHash(option_groups):\n", 2)
        result += tabulate(
            f'logging.warning(f"ConfigProxy: Config option groups hash is different from actual option groups")\n', 3
        )
        result += tabulate(
            f'logging.warning(f"ConfigProxy: This can be a sign that config is outdated and needs recreation")\n', 3
        )
        result += tabulate(f"{IConfig.__name__}.__init__({parameter_names})\n", 2)
        result += "\n".join(properties)

        if not isort.check_code(result):
            logging.info("Generator: Sorting imports with isort")
            result = isort.code(result)
        result = black.format_str(result, mode=black.Mode(line_length=120))

        with open(self.output, "wt") as f:
            f.write(result)


def getObjectLocation(location: str) -> tuple[str, str]:
    tmp: list[str] = location.split(":")
    if len(tmp) != 2:
        raise ValueError(f"Expected object location in 'module:object' format, got: '{location}'")
    return tmp[0], tmp[1]


def generateConfigProxy() -> None:
    logging.basicConfig(
        format="%(levelname)-5s | %(filename)s->%(funcName)s(%(lineno)d):    %(message)s",
        level=logging.DEBUG,
        stream=sys.stderr,
        force=True,
    )
    arg_parser = ArgumentParser()
    arg_parser.add_argument("module", type=getObjectLocation)
    arg_parser.add_argument("output", type=Path)
    args = arg_parser.parse_args()

    module_name, object_name = args.module
    output: Path = args.output

    # This script is supposed to be evoked only via library scripts mechanism (defined in pyproject.toml).
    # Doing so doesn't add current path to sys.path (opposed to running it with `python -m ...`).
    # This leads to broken imports, that's why we need to insert current path manually.
    sys.path.append(os.getcwd())

    generator: Generator = Generator(module_name, object_name, output)
    generator.generate()
