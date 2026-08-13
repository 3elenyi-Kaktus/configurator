from argparse import ArgumentParser
from dataclasses import dataclass, field
from importlib import util
import inspect
from inspect import Parameter, Signature, signature
import logging
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import EllipsisType, NoneType, UnionType
from typing import Any, ForwardRef, TypeVar, Union, get_args, get_origin

from ruff import find_ruff_bin

from kaktus.configurator._version import __version__
from kaktus.configurator.config import IConfig
from kaktus.configurator.option_group import OptionGroup


def tabulate(line: str, indent: int) -> str:
    return " " * 4 * indent + line


def formatGeneratedCode(source: str, stdin_filename: str) -> str:
    """Sort imports and format generated source with Ruff (isolated from consumer config)."""
    ruff = str(find_ruff_bin())
    isolated = ["--isolated", "--config", "line-length = 120"]
    isort_config = [
        *isolated,
        "--config",
        "lint.isort.lines-after-imports = 2",
        "--config",
        "lint.isort.combine-as-imports = true",
        "--config",
        "lint.isort.force-sort-within-sections = true",
    ]
    sorted_src = subprocess.run(
        [
            ruff,
            "check",
            "--select",
            "I",
            "--fix-only",
            *isort_config,
            "--stdin-filename",
            stdin_filename,
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return subprocess.run(
        [
            ruff,
            "format",
            *isolated,
            "--stdin-filename",
            stdin_filename,
            "-",
        ],
        input=sorted_src,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@dataclass
class OptionInfo:
    name: str
    group_name: str
    config_name: str
    config_type: type
    runtime_type: type


@dataclass(eq=True, frozen=True)
class ImportData:
    module_name: str
    object_name: str | None = field(default=None)


class Generator:
    def __init__(self, module_name: str, object_name: str, output: Path, command: str) -> None:
        self.module_name: str = module_name
        self.object_name: str = object_name
        self.output: Path = output
        self.command: str = command

        self.option_groups: list[type[OptionGroup]] = self.loadOptionGroups()
        self.imports: set[ImportData] = {
            ImportData("logging"),
            ImportData("kaktus.configurator.config", "IConfig"),
        }

    def loadOptionGroups(self) -> list[type[OptionGroup]]:
        logging.info(f"Generator: Loading module '{self.module_name}' with target object: {self.object_name}")
        spec = util.find_spec(self.module_name)
        logging.info(f"Generator: Loaded spec: {spec}")
        if spec is None:
            raise ModuleNotFoundError(f"Module '{self.module_name}' not found")
        module = util.module_from_spec(spec)
        sys.modules[self.module_name] = module
        spec.loader.exec_module(module)

        # Retrieve the list of option groups
        groups: list[type[OptionGroup]] = getattr(module, self.object_name)
        if (
            not isinstance(groups, list)
            or not all(isinstance(x, type) for x in groups)
            or not all(issubclass(x, OptionGroup) for x in groups)
        ):
            raise TypeError(
                f"Invalid option group listing: {groups} (expected 'list[type[OptionGroup]]', got: '{type(groups)}')"
            )
        return groups

    def addImport(self, tp: Any) -> None:
        logging.info(f"Generator: Adding import for class '{tp}'")
        try:
            module: str = tp.__module__
            qualname: str = tp.__qualname__
        except AttributeError as exc:
            logging.exception(exc)
            logging.error("Generator: Failed to generate import")
            return
        if module == "builtins":
            logging.info("Generator: Source is a 'builtins' module, skipping")
            return
        top_level_name = qualname.split(".", 1)[0]
        logging.info(
            f"Generator: Source module: '{tp.__module__}', qualified name: '{tp.__qualname__}', import target: '{top_level_name}'"
        )
        self.imports.add(ImportData(module, top_level_name))

    def _simplifyType(self, tp: Any) -> str:
        if isinstance(tp, TypeVar):
            raise TypeError("Using TypeVar's in config options is prohibited")

        if tp is None or tp is NoneType:
            return "None"
        if isinstance(tp, EllipsisType):
            return "..."
        if isinstance(tp, str):
            return tp
        if isinstance(tp, ForwardRef):
            return tp.__forward_arg__
        if isinstance(tp, list):
            return f"[{', '.join(map(self.simplifyType, tp))}]"

        origin = get_origin(tp)

        # X | Y
        if origin is UnionType or origin is Union:
            return " | ".join(self.simplifyType(x) for x in get_args(tp))

        # list[...], dict[...], Literal[...], Annotated[...], ...
        if origin is not None:
            self.addImport(origin)
            name = getattr(origin, "__name__", None) or getattr(origin, "_name", None) or self.simplifyType(origin)
            args = get_args(tp)
            if not args:
                return name

            inners: list[str] = []
            for arg in args:
                # If we are inside other type, treat strings as a literals
                if isinstance(arg, str):
                    inners.append(f"'{arg}'")
                else:
                    inners.append(self.simplifyType(arg))
            return f"{name}[{', '.join(inners)}]"

        self.addImport(tp)

        # Plain classes
        if isinstance(tp, type):
            return tp.__qualname__

        # Any and similar special forms
        return getattr(tp, "__name__", str(tp))

    def simplifyType(self, tp: Any) -> str:
        logging.info(f"Generator: Simplifying type '{tp}'")
        result: str = self._simplifyType(tp)
        logging.info(f"Generator: Simplified: '{tp}' -> '{result}'")
        return result

    def createProperty(self, option_info: OptionInfo) -> list[str]:
        config_type_string: str = self.simplifyType(option_info.config_type)
        runtime_type_string: str = self.simplifyType(option_info.runtime_type)
        res = [
            "@property\n",
            f"def {option_info.name}(self) -> {runtime_type_string}:\n",
            f"    return self._getOptionValue({option_info.group_name}.{option_info.config_name})  # type: ignore[no-any-return]\n\n",
            f"@{option_info.name}.setter\n",
            f"def {option_info.name}(self, value: {config_type_string}) -> None:\n",
            f"    self._setOptionValue({option_info.group_name}, {option_info.group_name}.{option_info.config_name}, value)\n",
        ]
        return res

    def getImports(self) -> list[str]:
        imports: list[str] = []
        for import_data in self.imports:
            if import_data.object_name is None:
                imports.append(f"import {import_data.module_name}")
            else:
                imports.append(f"from {import_data.module_name} import {import_data.object_name}")
        return imports

    def mangleConfigInit(self) -> str:
        logging.info("Generator: Creating '__init__' signature for ConfigProxy")
        init_signature: Signature = inspect.signature(IConfig.__init__)
        logging.info(f"Generator: Mangling the {IConfig} class '__init__': {init_signature}")
        simplified_params: list[str] = []
        for param in init_signature.parameters.values():
            param_str: str = param.name
            if param.annotation is not Parameter.empty:
                param_str += f": {self.simplifyType(param.annotation)}"
            if param.default is not Parameter.empty:
                param_str += f" = {param.default}"
            simplified_params.append(param_str)
        result: str = f"({', '.join(map(str, simplified_params))})"
        logging.info(f"Generator: Changed the '__init__' signature to: {result}")
        return result

    def generate(self) -> None:
        option_infos: list[OptionInfo] = []
        for option_group in self.option_groups:
            option_group_name = option_group.__name__
            logging.info(f"Generator: Loading options from group '{option_group_name}'")
            for option_name in option_group.getOptionAttrs():
                option = getattr(option_group, option_name)
                logging.info(f"Generator: Adding option: {option}")
                option_infos.append(
                    OptionInfo(option.name, option_group_name, option_name, option.in_type, option.rtype)
                )
        properties: list[str] = [
            "".join(tabulate(line, 1) for line in self.createProperty(option_info)) for option_info in option_infos
        ]

        for option_group in self.option_groups:
            self.addImport(option_group)

        init_params: str = self.mangleConfigInit()

        # We can collect imports only after finishing doing all the stuff related to type simplifying
        imports: list[str] = self.getImports()

        combined_hash: str = IConfig.getOptionGroupsHash(self.option_groups)

        newline: str = "\n"  # just a placeholder since 3.10 can't use backslashes in f-string expressions
        result: str = (
            f"# ----\n"
            f"# Automatically generated by configurator lib (v{__version__})\n"
            f"# Command used: {self.command}\n"
            f"# ----\n\n"
            f"{newline.join(imports)}"
            f"\n\n# ----\n"
            f"# Option groups hash signature:\n"
            f'_option_groups_hash: str = "{combined_hash}"\n'
            f"# ----\n\n"
            f"\n\nclass ConfigProxy({IConfig.__name__}):\n"
        )
        result += tabulate(f"def __init__{init_params} -> None:\n", 1)
        result += tabulate("if _option_groups_hash != IConfig.getOptionGroupsHash(option_groups):\n", 2)
        result += tabulate(
            'logging.warning("ConfigProxy: Config option groups hash is different from actual option groups. This can be a sign that config is outdated and needs recreation")\n',
            3,
        )
        parameter_names: str = ",".join(x for x in signature(IConfig.__init__).parameters)
        result += tabulate(f"{IConfig.__name__}.__init__({parameter_names})\n", 2)
        result += "\n".join(properties)

        logging.info("Generator: Formatting generated code with ruff")
        result = formatGeneratedCode(result, self.output.name)

        with open(self.output, "w") as f:
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

    generator: Generator = Generator(module_name, object_name, output, shlex.join(sys.argv))
    generator.generate()
