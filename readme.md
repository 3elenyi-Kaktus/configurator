# Configurator

### _by 3elenyi Kaktus_

A simple settings configurator for projects management.


## Usage concept

Usually, every project uses some kind of settings file, either a python file with defined constants, `YAML`/`JSON` files or just a hardcoded ones. In my own opinion (which may not always be the right one), the proper way of dealing with configs is using pure config files like `YAML` and `JSON`.

Using string literals inside the code is cumbersome: renaming options is a refactor hell, you can't track their usage via IDE tools and a single typo can ruin the whole app. This configurator narrows down possible places of mistake by using option string literals only in two places: their definitions in config and actual config files.



## Installation
The main target Python version is `3.10`. Correctness of work in any other version is not guaranteed.

```bash
pip install kaktus-configurator
```

Drawing option-dependency graph images (`--option-graphs-dirpath`) needs the optional extra:

```bash
pip install 'kaktus-configurator[graphs]'
```

## Setting up from scratch
We will further imply that user defined files are stored in a `settings/` directory.

Create an empty `settings/` directory (with `__init__.py` file if needed) in a user-written codespace. The final directory structure will be commonly the following:

    └── settings
        ├── configs
        │   ├── default.json
        │   └── test.json
        ├── envs
        │   ├── .env
        │   └── test.env
        ├── __init__.py
        ├── arg_parser.py
        ├── config.py
        ├── config_proxy.py
        ├── options.py
        └── version.py

Meaning and contents of every file will be explained in the next sections.



### Options creation
Every option is an instance with a configurable typecheckers and validators.

When listing options, it's preferable to use style like:

```python
# options.py
from kaktus.configurator.option_group import OptionGroup
from kaktus.configurator.option import Option


class MyOption(OptionGroup):
    OPTION_ONE = Option("option_one", rtype=str)
    OTHER_OPTION = Option("other_option", rtype=int, required=False)
```
String literals should be unique, since there is no way to distinguish them [TODO](#indev-features).

These option collections will then be passed to the config class for further work.

### Option class
Its instance holds all information about the option:
* `name`

  Specifies, well, the option name in config.
* `in_type`

  Option value type in config file. If it mismatches with actual type on config validation, the configurator will autofail the process.

  **Disclaimer**: Configurator (for now) supports only simple types, such as `list`, `str`, `bool`, etc. Complex types (such as `list[int]` or `tuple[int, str]`) won't work from the box, use custom validators for them.
* `rtype`

  Option value type after validation. Used to create a concrete typing while auto-generating proxy config file.
* `validator`

  Validation function (or basically any callable), which will be applied to the read value on config initialization. You can perform your own typechecks in it, and modify final value as you want. Default validation just forwards value through implementation without any modifications.
* `default`

  A default value in a form of a raw one (which would be loaded from config otherwise).
* `required`

  Required flag specifies if this option is actually needed to be specified in any of the sources. If set to `False` and option is not present, configurator will simply skip it. If a flagged option is accessed later in runtime, it will hold `None` value. This parameter is syntactically exclusive with the `default` one, if set to `False`.
* `dependencies`

  A dependency ruleset, refer to the [Dependencies](#dependencies-1) section for more information.

By default, configurator will check that all registered options are present in loaded config in any way: via config file, command line or `.env` file. If any of the options was not found, or if configurator found an unregistered option, it will fail the process.

Configurator needs option input type (which is retrieved from config file or other sources) and final option value (to correctly auto-generate proxy files). These types can be inferred automatically from the `validator` function, if it's a typed one. Otherwise (`validator` isn't a typed one, or you want to narrow down the types, if the `validator` ones are too broad for this exact case), you have to specify the types manually. Both `in_type`/`rtype` have higher precedence over the `validator` types. In the case when there is no `validator` function defined at all, you can omit the `in_type` and use only the `rtype` parameter (since raw values will be simply forwarded through and types won't change at all).

#### Important note 1 (todo)
If option is set as not required, there is no way (for now) to determine, if it was completely omitted in all sources or intentionally set to value `None` [TODO](#indev-features).

#### Important note 2
There are some system options, that are already defined for library usage and injected directly to the base configurator class. Do not override them or create options with similar names. Refer to the [System Options](#system-options) section.


### CMD arguments parser
Configurator supports command line arguments. If needed, you'll have to create a new `ArgParser` class like this:

```python
# arg_parser.py
from kaktus.configurator.arg_parser import IArgParser
from settings.options import MyOption
from settings.version import __version__


class ArgParser(IArgParser):
    def __init__(self) -> None:
        super().__init__(f"App description, v{__version__}")
        self.parser.add_argument(
            "--my-awesome-option",
            required=False,
            help="Some useful description",
            dest=MyOption.OPTION_ONE.name,
        )
        self.parser.add_argument(...)
```

You can tweak the parser options as you want, using the standard `argparse` library guidelines.

#### Important note 1
I recommend to use the separate file, dedicated to storing the app version info. Though, using the versioning is completely up to user and can be skipped.

#### Important note 2
Naming of `ArgParser` options has nothing to do with option names, defined in config. You can name them as you want (i.e. `--my-awesome-option`), given that their destinations are set to one of `MyOptionName` names.

#### Important note 3
There are some reserved argument names for system options, which shouldn't be used. Refer to [System Options](#system-options) section.



### Config
The config class itself, is a simple wrapper with the properties, which point to the corresponding options. To create one, you can either:
1) Use the config auto-generator, which will automatically collect the options and infer the correct getters/setters for them in a separate `ConfigProxy` class. I recommend using the `config_proxy.py` file to store this generated content. Then, you'll need only the simple wrapper around this class to fine-grain the argument parser or other config parameters:

```python
# config.py
from settings.arg_parser import ArgParser
from settings.config_proxy import ConfigProxy
from settings.options import option_groups


class Config(ConfigProxy):
    def __init__(self) -> None:
        arg_parser: ArgParser = ArgParser()
        ConfigProxy.__init__(self, option_groups, arg_parser=arg_parser)
        self._recreate()
```

To regenerate the config proxy, simply run the command: `config-regen option.listing.module.location:variable_name path/to/output.py`. For this to work, you have to create a variable in the options listing file, holding all the option classes as a list:

```python
# options.py
from kaktus.configurator.option_group import OptionGroup

option_groups: list[type[OptionGroup]] = [MyOption, ...]
```

2) (discouraged) You can subclass `IConfig` class directly and write getters for your own options manually. You'll have to manually change all the function signatures on a simple value typing or option name changes, though. This is considered more impractical by me, but may be viable in some cases:

```python
# config.py
from kaktus.configurator.config import IConfig
from settings.arg_parser import ArgParser
from settings.options import MyOption


class Config(IConfig):
    def __init__(self) -> None:
        # If you're not using your own argument parser, use IArgParser instance instead
        arg_parser: ArgParser = ArgParser()
        IConfig.__init__(self, [MyOption], arg_parser=arg_parser)
        self._recreate()

    @property
    def option_one(self) -> str:
        return self._getOptionValue(MyOption.OPTION_ONE)

    @option_one.setter
    def option_one(self, value: str) -> None:
        self._setOptionValue(MyOption, MyOption.OPTION_ONE, value)
```

#### Important note

Since options are generally static, there is no use to import them one by one and pass them as a separate arguments to Config class. They can be grouped into a list in the options listing file and imported directly from it, as shown in the method above

```python
# config.py
from kaktus.configurator.config import IConfig
from settings.options import option_groups


class Config(IConfig):
    def __init__(self):
        ...
        IConfig.__init__(self, option_groups, ...)
        ...
```


### System options
As was stated before, some options are already defined at library level. These are:
* Path to config file, from which all options are retrieved.

    Config name: `"config_filepath"`

    CMD name: `-p` (short for `--config-filepath`)
* Optional path to `.env` file with analogical purposes.

    Config name: `"env_filepath"`

    CMD name: `--env-filepath`
* Optional path to the directory, where option dependency graph images will be dumped.

    Config name: `"option_graphs_dirpath"`

    CMD name: `--option-graphs-dirpath`
#### Important note
Technically, path to config file is a required option. But since it can only effectively be defined in CMD arguments, in reality it's never written in config file.



### `.env` files
Strictly speaking, config file and `.env` file hold the exactly same purpose. But, they differ in some ways:
- `.env` files (for now) support only `int` and `str` types [TODO](#indev-features).
- Option names in `.env` files should be written in uppercase, instead of lowercase.

`.env` file functionality is added for security reasons: holding sensitive information, such as passwords, which mustn't be published in open sources.

To specify whether value is a `str` or `int`, wrap it in single or double quotes for `str`, otherwise, value is considered to be an `int`.

Typical file will look like:
```dotenv
# Postgres connector
POSTGRES_USER='my_user'
POSTGRES_PASSWORD='my_password'
POSTGRES_HOST='127.0.0.1'
POSTGRES_PORT=5432
```

You can define path to `.env` file either in config file, using the `"env_filepath"` system option, or passing it via CMD args with `--env-filepath`.

#### Important note
`.env` files are parsed with a custom parser, which won't add these variables to the environment, only to the config class. On the other hand, creating environment with these variables in it won't impact the program, since we don't read any environment at all. Therefore, its `.env` name is only for hinting that these options are private ones and shouldn't be saved in a repository or anywhere else.



### Option source priorities
Option sources have a strict priority over each one:
$$CMD\ options \gt File\ options \gt\ .env\ options$$
If any of options is redeclared in another source, only value from the one with the highest source priority will be used.

### Usage

After you listed all the needed options and prepared the config class, you are ready to use configurator. Simply create its instance and use it to access the options:

```python
# some_user_file.py
from settings.config import Config


config: Config = Config()
print(f"My awesome option: {config.option_one}")
```

Minimal requirement to start a program using this library is passing a path to config file at start:
```bash
python my_program.py -p path/to/config.json
```



### Exclusive option groups
Imagine, you program has options `PRINT_FLAG` and `FIBO_NUMBER` and depending on which one of 2 options was set, it either prints "Hello world!" or counts Nth Fibonacci number. And you expect someone to do only one of the things at once. What if both options are defined at the same time?

You can certainly write some internal program logic, which detects these situations and resolves it as needed. But when amount of options and their possible combinations goes up, this can become a problematic task.

To solve this, you can use exclusive group rules:

```python
# options.py
from kaktus.configurator.rules import ExclusiveGroupRule

exclusive_group_rules: list[ExclusiveGroupRule] = [
    (
        (MyOption.PRINT_FLAG.name,),
        (MyOption.FIBO_NUMBER.name,),
    ),
]
```

Each inner tuple is a group of **option names**. If `PRINT_FLAG` is defined, then config will automatically fail the start if `FIBO_NUMBER` is defined too and vice versa.

If there are multiple options to be excluded (for example, in mode 2 we can use `TIMEOUT`, to throw an error if number wasn't computed in time), they can be used at once in a single rule:

```python
# options.py
from kaktus.configurator.rules import ExclusiveGroupRule

exclusive_group_rules: list[ExclusiveGroupRule] = [
    (
        (MyOption.PRINT_FLAG.name,),
        (MyOption.FIBO_NUMBER.name, MyOption.TIMEOUT.name),
    ),
]
```
In this case, both `PRINT_FLAG` and `TIMEOUT` can be defined at once, but if `PRINT_FLAG` is defined, defining any of `FIBO_NUMBER` and `TIMEOUT` will result in error.

#### Important note
If using exclusive option groups, for every exclusive group you have to set options `required` flag as if all other groups are non-present and this option group is the only one to be validated.



### Dependencies
In previous example we excluded usage of option `TIMEOUT` if `PRINT_FLAG` is defined. Usually this design would work ok, but generally speaking this is a wrong pattern for this case, since we tried to solve a bit different problem. Firstly, if we have a lot of options, which are used exclusively in mode 1 or in mode 2, these lists of option groups will grow indefinitely, making it troublesome to maintain them. Secondly, the root of our problem was not in having both `TIMEOUT` and `PRINT_FLAG` set at the same time (setting these options most possibly won't lead to any kind of problems, since they are used in completely different submodules of our program), but rather having `TIMEOUT` set when `FIBO_NUMBER` is not defined.

So basically, we want to solve another problem: one option depends on another one and can be set only if all of its dependencies are fulfilled. For this case we can use dependency rules with `Depends` directive, when creating `Option` objects:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup
from kaktus.configurator.rules import Depends


class MyOption(OptionGroup):
    FIBO_NUMBER = Option("fibo_number", rtype=int, required=False)
    TIMEOUT = Option("timeout", rtype=float, required=False, dependencies=Depends(FIBO_NUMBER))
```

Here, if somehow `TIMEOUT` is defined, while `FIBO_NUMBER` is not set, configurator will detect this problem.

You can chain `Depends` rules with `&` and `|` operators for **AND**ing and **OR**ing conditions respectively. For example, if we want to compute several Fibo numbers `FIBO_NUMBER_1` and `FIBO_NUMBER_2`:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup
from kaktus.configurator.rules import Depends


class MyOption(OptionGroup):
    FIBO_NUMBER_1 = Option("fibo_number_1", rtype=int, required=False)
    FIBO_NUMBER_2 = Option("fibo_number_2", rtype=int, required=False)
    # Timeout if any of the Fibo numbers (or both) will be computed
    TIMEOUT_ANY = Option(
        "timeout_any",
        rtype=float,
        required=False,
        dependencies=Depends(FIBO_NUMBER_1) | Depends(FIBO_NUMBER_2),
    )
    # Timeout only when computing both numbers at once
    TIMEOUT_BOTH = Option(
        "timeout_both",
        rtype=float,
        required=False,
        dependencies=Depends(FIBO_NUMBER_1) & Depends(FIBO_NUMBER_2),
        # or an equivalent
        dependencies=Depends(FIBO_NUMBER_1, FIBO_NUMBER_2),
    )
```

#### Important note
If using dependencies for option, you have to set its `required` flag as if its dependencies are fulfilled and option can be used freely.



### Online reloading (hot reload)
Sometimes, it's a waste to stop the whole program just to change its log level from `INFO` to `DEBUG`. To solve this problem, config supports hot reloading.

It polls the provided config file for changes if needed. On file change, config is revalidated and all changed options are reevaluated. To leverage this functionality, config must be provided with a callback and list of options, which change will trigger specified callback. If any of callback's checked options are changed, the callback will be called with the list of specified options. It's callback's responsibility to check which of the options exactly changed and how to deal with them.

To enable hot reloading you have to set it up:

```python
# some_user_file.py
config.enableHotReload()
```

On program exit (or whenever needed), you should disable it (otherwise it won't stop polling by itself):

```python
# some_user_file.py
config.atExit()
```

If you have an instance of a config, simply add needed callbacks to it.
For example, if you have options `my_foo` and `my_bar`:

```python
# some_user_file.py
def foo(option) -> None:
    print(f"Option foo changed: {option}")


def bar(option) -> None:
    print(f"Option bar changed: {option}")


def foobar(option_foo, option_bar) -> None:
    print(f"Both foo and bar changed at once! Foo: {option_foo}, bar: {option_bar}")


# Notice the important difference: we attach callback to an **instance**, but we list checked options from **class**!
config.addReloadCallback(
    foo,
    [Config.my_foo],
)
config.addReloadCallback(
    bar,
    [Config.my_bar],
)
# In case of both foo and bar changing, all three callbacks (foo, bar and foobar) will be fired
config.addReloadCallback(foobar, [Config.my_foo, Config.my_bar])
```

#### Important note
Due to design, arguments passed via command line can't be changed in runtime, since their values are immutable and preferred over other ones. If you plan to change arguments in runtime, consider limiting amount of arguments passed in CMD on program start as much as possible.

## Option groups
When your config grows over time, it can be hard to differentiate options for one module from other ones. The basic approach is prepending option names with respective module name:
```json
{
  "fibo_option_1": 1,
  "fibo_option_2": 2,
  "parser_option_a": "a",
  "parser_option_b": "b"
}
```
If there are even more levels of submodules, this schema can become quite tedious to handle. There's a solution for these cases: splitting options into specialized groups. In terms of config, it would look this way:
```json
{
  "fibo": {
    "option_1": 1,
    "option_2": 2
  },
  "parser": {
    "option_a": "a",
    "option_b": "b"
  }
}
```
This method can handle any amount of submodule levels in a more simple manner. To describe such structure in Python, you can use `@optionGroup` decorator. You can create a base class first, to bind groups to it:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import optionGroup, OptionGroup


class BaseOption(OptionGroup):
    pass


@optionGroup(parent=BaseOption, prefix="fibo")
class FiboOption(OptionGroup):
    OPTION_1 = Option("option_1", rtype=int)
    OPTION_2 = Option("option_2", rtype=int)


@optionGroup(parent=BaseOption, prefix="parser")
class ParserOption(OptionGroup):
    OPTION_A = Option("option_a", rtype=str)
    OPTION_B = Option("option_b", rtype=str)
```
This is not a necessary step, since if parent is not specified, configurator will unwrap these groups as if they were bound to the root one.

Under the hood before trying to read options from config, configurator will try to flatten it first, using combinations of prefixes and parents, acquired from option groups. Basically, this means that configurator will iteratively walk up the tree from leaves, adding the prefix to all options in current group and adding them to the parent, repeating until no groups are left. Mentioned config will be thus reduced to the equivalent of the following one:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import OptionGroup


class BaseOption(OptionGroup):
    pass


class FiboOption(OptionGroup):
    OPTION_1 = Option("fibo_option_1", rtype=int)
    OPTION_2 = Option("fibo_option_2", rtype=int)


class ParserOption(OptionGroup):
    OPTION_A = Option("parser_option_a", rtype=str)
    OPTION_B = Option("parser_option_b", rtype=str)
```

With this setup both beforementioned config variants will work fine: first one will be used as is, and the second one will be transformed to the first one.

`@optionGroup` decorator takes up 3 arguments:
* `parent` - Parent class, mentioned before.
* `prefix` - Prefix, which will be added to option names on unwrapping.
* `real` - Flag if group is a real one.

The last one shows if specified prefix should be added to the real option name. The default behavior is to add the prefix. Otherwise, configurator will use this prefix while unwrapping the config, but won't add it to the option names, forwarding them as is.

For example, you can create a virtual `limits` group with real `http` / `worker` children:

```json
{
  "limits": {
    "http": {
      "max_connections": 10
    },
    "worker": {
      "pool_size": 4
    }
  }
}
```

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import optionGroup, OptionGroup


@optionGroup(prefix="limits", real=False)
class LimitsProxy(OptionGroup):
    pass


@optionGroup(parent=LimitsProxy, prefix="http")
class HttpLimits(OptionGroup):
    MAX_CONNECTIONS = Option("max_connections", rtype=int)


@optionGroup(parent=LimitsProxy, prefix="worker")
class WorkerLimits(OptionGroup):
    POOL_SIZE = Option("pool_size", rtype=int)
```

JSON file still nests options under `"limits"` section (as it would do with syntactic sugar grouping), but option names will stay `http_max_connections` and `worker_pool_size` — not `limits_http_max_connections`. As this is purely a syntactic sugar, you have to be aware that defining options with same names in different virtual groups would still result in an error.

## Inheritance
If you have multiple option groups with common options, you can use inheritance alongside the `@optionGroup` decorator:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import optionGroup, OptionGroup


class CommonOption(OptionGroup):
    TIMEOUT = Option("timeout", rtype=float)


@optionGroup(prefix="fibo")
class FiboOption(CommonOption):
    OPTION_1 = Option("option_1", rtype=int)


@optionGroup(prefix="parser")
class ParserOption(CommonOption):
    OPTION_A = Option("option_a", rtype=str)
```
This is equivalent to the following:

```python
# options.py
from kaktus.configurator.option import Option
from kaktus.configurator.option_group import optionGroup, OptionGroup


@optionGroup(prefix="fibo")
class FiboOption(OptionGroup):
    OPTION_1 = Option("option_1", rtype=int)
    TIMEOUT = Option("timeout", rtype=float)


@optionGroup(prefix="parser")
class ParserOption(OptionGroup):
    OPTION_A = Option("option_a", rtype=str)
    TIMEOUT = Option("timeout", rtype=float)
```
Please note, that using `@optionGroup` with prefixes in these situations is crucial. If no prefix is specified, this would basically mean creating 2 options with same names, which will lead to undefined behavior.

# InDev features

Tracked in more detail in [`todo.md`](todo.md).
