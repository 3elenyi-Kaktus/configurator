# Configurator

### _by 3elenyi Kaktus_

A simple settings configurator for projects management.



# Usage concept

Usually, every project uses some kind of settings file, either a python file with defined constants, YAML/JSON files or just a hardcoded ones.
In my own opinion (which may not always be the right one), the proper way of dealing with configs is using pure config files like YAML and JSON.

Using string literals inside the code is cumbersome: renaming options is a refactor hell, you can't track their usage via IDE tools and a single typo can ruin the whole app.
This configurator narrows down possible places of mistake by using option string literals only in two places: their definitions in config and actual config files.



# Dependencies
The main target Python version is `3.10`. Correctness of work in any other version is not guaranteed.

This library depends on a custom `json-helpers` library, which is used to print pretty JSON's in logs.



# Setting up from scratch
We will further imply that user defined files are stored in a `settings/` directory.

Create a `settings/` directory (with `__init__.py` file if needed) in a user-written codespace.
The directory structure will be commonly the following:

    └── settings
        ├── configs
        │   ├── default_config.json
        │   └── test_config.json
        ├── .env
        ├── __init__.py
        ├── arg_parser.py
        ├── config.py
        ├── options.py
        └── version.py

Meaning and contents of every file will be explained in the next sections.



### Options creation
Every option is an instance with a configurable typecheckers and validators.

When listing options, it's preferable to use style like:

```python
from configurator.option_group import OptionGroup
from configurator.option import Option

class MyOption(OptionGroup):
    OPTION_ONE = Option("option_one", str)
    OTHER_OPTION = Option("other_option", int, required=False)
```
String literals should be unique, since there is no way to distinguish them [TODO](#indev-features).

These option collections must be passed to the config class for further work.

### Option class
Its instance holds all information about the option:
* `name`

    Specifies, well, the option name in config.
* `config_inner_type`

    Option value type in config file.
If it mismatches with actual type on config validation, the configurator will autofail the process.

    **Disclaimer**: Configurator (for now) supports only simple types, such as `list`, `str`, `bool`, etc.
Complex types (such as `list[int]` or `tuple[int, str]`) won't work from the box, use custom validators for them.
* `validator`

    Validation function, which will be applied to the read value of specified option on its initialization.
You can perform your own typechecks in it, and modify final value as you want.
Default validation just forwards value through implementation without any modifications.
* `required`

    Required flag specifies if this option is actually needed to be specified in any of the sources.
If set to `False` and option is not present, configurator will simply skip it.
If this option is accessed later in runtime, it will hold `None` value.
* `dependencies`

    A dependency rule, refer to the [Dependencies](#dependencies-1) section for more information.
* `value`

    The converted value of option itself.

By default, configurator will check that all registered options are present in loaded config in any way: via config file, command line or `.env` file.
If any of the options was not found, or if configurator found an unregistered option, it will fail the process.


#### Important note 1 (todo)
If option is set as not required, there is no way (for now) to determine, if it was completely omitted in all sources or intentionally set to value `None` [TODO](#indev-features).

#### Important note 2
There are some system options, that are already defined for library usage and injected directly to the base configurator class.
Do not override them or create options with similar names.
Refer to the [System Options](#system-options) section.


### CMD arguments parser
Configurator supports command line arguments. If needed, you'll have to create a new `ArgParser` class like this:

```python
import argparse
from configurator.arg_parser import IArgParser
from settings.options import MyOption
from settings.version import __version__


class ArgParser(IArgParser):
  def __init__(self) -> None:
    super().__init__(f"App description, v{__version__}")
    self.parser.add_argument(
      "--my-awesome-option",
      required=False,
      default=argparse.SUPPRESS,
    help = "Some useful description",
    dest = MyOption.OPTION_ONE.name,
    )
    self.parser.add_argument(...)
```

You can tweak the parser options as you want, using the standard `argparse` library guidelines. The only requirement is adding `default=argparse.SUPPRESS` if option isn't required and has no default value.

#### Important note 1
Naming of `ArgParser` options has nothing to do with option names, defined in config.
You can name them as you want (i.e. `--my-awesome-option`), given that their destinations are set to one of `MyOptionName` names.

#### Important note 2
There are some reserved argument names for system options, which shouldn't be used.
Refer to [System Options](#system-options) section.



### Config
The config class itself, is a simple wrapper with the getter functions. To create one, you should subclass it and write getters for your own options:

```python
from typing import Optional
from configurator.config import IConfig
from settings.arg_parser import ArgParser
from settings.options import MyOption


class Config(IConfig):
    def __init__(self):
        arg_parser: ArgParser = ArgParser()
        # if you're not using your own argument parser, use IArgParser instance instead
        super().__init__([MyOption], arg_parser=arg_parser)
        self._recreate()

    @property
    def option_one(self) -> Optional[str]:
        return self._getOptionValue(MyOption.OPTION_ONE)
```

#### Important note

Since options are generally static, there is no use to pass them as arguments to Config class.
They can be imported directly from the file.



### System options
As was stated before, some options are already defined at library level.
These are:
* Path to config file, from which all options are retrieved.

    Config name: `"config_filepath"`

    CMD name: `-p` (short for `--config-filepath`)
* Optional path to `.env` file with analogical purposes.

    Config name: `"env_filepath"`

    CMD name: `--env-filepath`

#### Important note
Technically, path to config file is a required option too.
But since it can only effectively be defined in CMD arguments, in reality it's never written in config file.



### `.env` files
Strictly speaking, config file and `.env` file hold the exactly same purpose.
But, they differ in some ways:
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
`.env` files are parsed with a custom parser, which won't add these variables to the environment, only to the config class.
On the other hand, creating environment with these variables in it won't impact the program, since we don't read any environment at all.
Therefore, its `.env` name is only for hinting that these options are private ones and shouldn't be saved in a repository or anywhere else.



### Option source priorities
Option sources have a strict priority over each one:
$$CMD\ options \gt File\ options \gt\ .env\ options$$
If any of options is redeclared in another source, only value from the one with the highest source priority will be used.

### Usage

After you created all the needed options, you are ready to use configurator.
Simply create its instance and use it for access the options:

```python
from settings.config import Config

config: Config = Config()
print(f"My awesome option: {config.option_one}")
```

Minimal requirement to start a program, using this library is passing a path to config file at start:
```bash
python my_program.py -p path/to/config.json
```



### Exclusive option groups
Imagine, you program has options `PRINT_FLAG` and `FIBO_NUMBER` and depending on which one of 2 options was set, it either prints "Hello world!" or counts Nth Fibonacci number.
And you expect someone to do only one of the things at once.
What if both options are defined at the same time?

You can certainly write some internal program logic, which detects these situations and resolves it as needed.
But when amount of options and their possible combinations goes up, this can become a problematic task.

To solve this, you can use exclusive group rules:

```python
from configurator.rules import ExclusiveGroupRule

exclusive_group_rules: list[ExclusiveGroupRule] = [
    (
        (MyOption.PRINT_FLAG,),
        (MyOption.FIBO_NUMBER,),
    ),
]
```

If `PRINT_FLAG` is defined, then config will automatically fail the start if `FIBO_NUMBER` is defined too and vice versa.

If there are multiple options to be excluded (for example, in mode 2 we can use `TIMEOUT`, to throw an error if number wasn't computed in time), they can be used at once in a single rule:

```python
from configurator.rules import ExclusiveGroupRule

exclusive_group_rules: list[ExclusiveGroupRule] = [
    (
        (MyOption.PRINT_FLAG,),
        (MyOption.FIBO_NUMBER, MyOption.TIMEOUT),
    ),
]
```
In this case, both `PRINT_FLAG` and `TIMEOUT` can be defined at once, but if `PRINT_FLAG` is defined, defining any of `FIBO_NUMBER` and `TIMEOUT` will result in error.

#### Important note
If using exclusive option groups, for every exclusive group you have to set options `required` flag as if all other groups are non-present and this option group is the only one to be validated.



### Dependencies
In previous example we excluded usage of option `TIMEOUT` if `PRINT_FLAG` is defined.
Usually this design would work ok, but generally speaking this is a wrong pattern for this case, since we tried to solve a bit different problem.
Firstly, if we have a lot of options, which are used exclusively in mode 1 or in mode 2, these lists of option groups will grow indefinitely, making it troublesome to maintain them.
Secondly, the root of our problem was not in having both `TIMEOUT` and `PRINT_FLAG` set at the same time (setting these options most possibly won't lead to any kind of problems, since they are used in completely different submodules of our program), but rather having `TIMEOUT` set when `FIBO_NUMBER` is not defined.

So basically, we want to solve another problem: one option depends on another one and can be set only if its dependencies are fulfilled.
For this case we can use dependency rules with `Depends` directive, when creating Option objects:

```python
from configurator.rules import Depends

Option(MyOption.TIMEOUT, float, dependencies=Depends(MyOption.FIBO_NUMBER)),
```

Here, if somehow `TIMEOUT` will be defined, if `FIBO_NUMBER` is not set, configurator will detect this problem.

You can chain `Depends` rules with `&` and `|` operators for **AND**ing and **OR**ing conditions respectively.
For example, if we want to compute several Fibo numbers `FIBO_NUMBER_1` and `FIBO_NUMBER_2`:

```python
from configurator.rules import Depends

# We want to use timeout, if any of Fibo numbers (or both) will be computed
Option(MyOption.TIMEOUT, float, dependencies=Depends(MyOption.FIBO_NUMBER_1) | Depends(MyOption.FIBO_NUMBER_2)),

# We want to use timeout only when computing both numbers at once
Option(MyOption.TIMEOUT, float, dependencies=Depends(MyOption.FIBO_NUMBER_1) & Depends(MyOption.FIBO_NUMBER_2)),
Option(MyOption.TIMEOUT, float, dependencies=Depends(MyOption.FIBO_NUMBER_1, MyOption.FIBO_NUMBER_2)), # Equivalent to the previous one
```

#### Important note
If using dependencies for option, you have to set its `required` flag as if its dependencies are fulfilled and option can be used freely.



### Online reloading (hot reload)
Sometimes, it's a waste to stop the whole program just to change its log level from Debug to Info.
To solve this problem, config supports hot reloading.

It polls the provided config file for changes if needed.
On file change, config is revalidated and all changed options are reevaluated.
To leverage this functionality, config must be provided with a callback and list of options, which change will trigger specified callback.
If any of callback's checked options are changed, the callback will be called with the list of specified options.
It's callback's responsibility to check which of the options exactly changed and how to deal with them.

To enable hot reloading you have to set it up:

```python
config.enableHotReload()
```

On program exit (or whenever needed), you should disable it (otherwise it won't stop polling by itself):

```python
config.atExit()
```

If you have an instance of a config, simply add needed callbacks to it.
For example, if you have options `my_foo` and `my_bar`:

```python
def foo(option) -> None:
    print(f"Option foo changed: {option}")

def bar(option) -> None:
    print(f"Option bar changed: {option}")

def foobar(option_foo, option_bar) -> None:
    print(f"Both foo and bar changed at once! Foo: {option_foo}, bar: {option_bar}")

# Notice the important difference: we attach callback to an **instance**, but we list checked options from **class**!
config.addReloadCallback(
    foo, [Config.my_foo],
)
config.addReloadCallback(
    bar, [Config.my_bar],
)
# In case of both foo and bar changing, all three callbacks will be fired
config.addReloadCallback(
    foobar, [Config.my_foo, Config.my_bar]
)
```

#### Important note
Due to design, arguments passed via command line can't be changed in runtime, since their values are immutable and preferred over other ones.
If you plan to change arguments in runtime, consider limiting amount of arguments passed in CMD on program start as much as possible.

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
class BaseOption(OptionGroup):
    pass

@optionGroup(parent=BaseOption, prefix="fibo")
class FiboOption(OptionGroup):
    OPTION_1 = Option("option_1", int)
    OPTION_2 = Option("option_2", int)

@optionGroup(parent=BaseOption, prefix="parser")
class ParserOption(OptionGroup):
    OPTION_A = Option("option_a", str)
    OPTION_B = Option("option_b", str)
```
This is not a necessary step, since if not parent specified, configurator will unwrap these groups as if they were bound to the root one.

Under the hood before trying to read options from config, configurator will try to flatten it first, using combinations of prefixes and parents, acquired from option groups. Basically, this means that configurator will iteratively walk up the tree from leaves, adding the prefix to all options in current group and adding them to the parent, repeating until no groups are left. Mentioned config will be thus reduced to the equivalent of the following one:

```python
class BaseOption(OptionGroup):
    pass

class FiboOption(OptionGroup):
    OPTION_1 = Option("fibo_option_1", int)
    OPTION_2 = Option("fibo_option_2", int)

class ParserOption(OptionGroup):
    OPTION_A = Option("parser_option_a", str)
    OPTION_B = Option("parser_option_b", str)
```

With this setup both beforementioned config variants will work fine: first one will be used as is, and the second one will be transformed to the first one.

`@optionGroup` decorator takes up 3 arguments:
* Parent class, mentioned before.
* Prefix, which will be added to option names on unwrapping.
* Flag if group is a real one.

The last one shows if specified prefix should be added to the real option name. The default behavior is to add the prefix. Otherwise, configurator will use this prefix while unwrapping the config, but won't add it to the option names, forwarding them as is.

# Inheritance
If you have multiple option groups with common options, you can use inheritance alongside the `@optionGroup` decorator:
```python
class CommonOption(OptionGroup):
    TIMEOUT = Option("timeout", float)

@optionGroup(prefix="fibo")
class FiboOption(CommonOption):
    OPTION_1 = Option("option_1", int)

@optionGroup(prefix="parser")
class ParserOption(CommonOption):
    OPTION_A = Option("option_a", str)
```
This is equivalent to the following:
```python
@optionGroup(prefix="fibo")
class FiboOption(OptionGroup):
    OPTION_1 = Option("option_1", int)
    TIMEOUT = Option("timeout", float)

@optionGroup(prefix="parser")
class ParserOption(OptionGroup):
    OPTION_A = Option("option_a", str)
    TIMEOUT = Option("timeout", float)
```
Please note, that using `@optionGroup` with prefixes in these situations is crucial. If no prefix is specified, this would basically mean creating 2 options with same names, which will lead to undefined behavior.

# InDev Features
## todo add method to base argparser which automatically suppresses arguments if they were not supplied (argparse.SUPPRESS)
## todo imports in \_\_all__
## todo check for duplicate options (use sets) in dependencies and exclusive groups
## todo autogenerate user config file
## todo do we really need Depends or these operators can be safely overloaded in optionName enum?
## todo do we need any other types (apart from int and str) in .env files?
## todo Configurable class
## todo Tests for invariants