# Configurator

### by 3elenyi Kaktus

A simple settings configurator for projects management.

# Usage concept

Usually, every project uses some kind of settings file, either a python file with defined constants, YAML/JSON files or just a hardcoded ones.
In my own opinion (which may not always be the right one), the proper way of dealing with configs is using pure config files like YAML and JSON.

Using string literals inside the code is cumbersome: renaming options is a refactor hell, you can't track their usage via IDE tools and a single typo can ruin the whole app.
This configurator narrows down possible places of mistake by using option string literals only in two places: their definitions in config and actual config files.

# Dependencies
The main target Python version is `Python 3.10`. Correctness of work in any other version is not guaranteed.

This library depends on a custom `lib/json` library, which is used to print pretty JSON's in logs.

# Setting up from scratch
We will further imply that library is stored in a `lib/` directory and user defined files are stored in a `settings/` directory.
The `lib/configurator/` directory is the main source of code.

Create a `settings/` directory (with `__init__.py` file if needed) in a user-written codespace. The directory structure will be commonly the following:

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
class MyOptionName(IOptionName):
    OPTION_ONE = "option_one"
    OTHER_OPTION = "other_option"
```
String literals should be unique, since there is no way to distinguish them.

All listed options must be registered via creating an Option objects:

```python
Option(MyOptionName.OPTION_ONE, Optional[str])
```

These option objects must be passed to the config class for further work.
Typically, you'll have a list of them:

```python
my_options: list[Option] = [
    Option(MyOptionName.OPTION_ONE, Optional[str]),
    Option(MyOptionName.OTHER_OPTION, int)
]
```

### Option class
Its instances hold all information about the option:
* Option name
* Type in config file
* Validation function
* Required or not flag
* And lastly, the loaded value of option itself

Disclaimer: Configurator (for now) supports only simple types, such as `list`, `str`, `bool`, etc.
Complex types (such as `list[int]` or `tuple[int, str]`) won't work, use custom validators for them.

Option value type in config file specifies, well, it's type.
If it mismatches with actual type on config validation, the configurator will fail the process.

Validation function is a function which will be applied to the read value of specified option on its initialization.
You can perform your own typechecks in it, and modify final value as you want.
Default validation just forwards value through implementation without any modifications.

By default, configurator will check that all registered options are present in loaded config in any way: via config file, command line or `.env` file.
If any of the options was not found, or if configurator found an unregistered option, it will fail the process.

Required flag specifies if this option is actually needed to be specified.
If it's not present, configurator will simply skip it.
If this option is accessed in runtime, it will hold `None` value.

#### Important note 1
If option is set as not required, there is no way (for now) to determine, if it was completely omitted in all sources or intentionally set to value `None`.

#### Important note 2
There are some system options, that are already defined for library usage and injected directly to the base configurator class.
Do not override them or create options with similar names.

### CMD arguments parser
Configurator supports command line arguments. If needed, you'll have to create a new `ArgParser` class like this:
```python
from lib.configurator.arg_parser import IArgParser
from settings.options import OptionName
from settings.version import __version__


class ArgParser(IArgParser):
    def __init__(self) -> None:
        super().__init__(f"App description, v{__version__}")
        self.parser.add_argument(
            "--my-awesome-option",
            required=False,
            help="Some useful description",
            dest=MyOptionName.OPTION_ONE,
        )
        self.parser.add_argument(...)
```

You can tweak the parser options as you want, using the standard `argparse` library guidelines.

#### Important note 1
Naming of `ArgParser` options has nothing to do with option names, defined in config.
You can name them as you want (i.e. `"--my-awesome-option"`), given that their destinations are set to one of `MyOptionName` names.

#### Important note 2
`"-p"` (short for `"--config-filepath"`) and `"--env-filepath"` are reserved for system options and shouldn't be used.

### Configurator
The config class itself, is a simple wrapper with the getter functions. To create one, you should subclass it and write getters for your own options:

```python
from lib.configurator.config import IConfig
from settings.arg_parser import ArgParser
from settings.options import MyOptionName, my_options as registered_options


class Config(IConfig):
    def __init__(self):
        arg_parser: ArgParser = ArgParser()
        # if you're not using your own argument parser, use IArgParser instance instead
        super().__init__(arg_parser, registered_options)
        self._recreate()

    @property
    def option_one(self) -> Optional[str]:
        return self._getOptionValue(MyOptionName.OPTION_ONE)
```

#### Important note

Since options are generally static, there is no use to pass them as arguments to Config class.
They can be imported directly from the file.

### System options
As was stated before, some options are already defined at library level.
These are:
- Path to config file, from which all options are retrieved.
- Optional path to `.env` file with analogical purposes.

#### Important note
Technically, path to config file is a required option too.
But since it can only effectively be defined in CMD arguments, in reality it's never written in config file.

### `.env` files
Strictly speaking, config file and `.env` file hold the exactly same purpose.
But, they differ in some ways:
- `.env` files (for now) support only `int` and `str` types.
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
Imagine, you program has options `Option1` and `Option2` and depending on which one of 2 options was set, either prints "Hello world!" or writes it to file.
And you expect someone to do only one of things at once.
What if both options are defined at the same time?

You can certainly write some internal program logic, which detects these situations and resolves it as needed.
But when amount of options and their possible combinations goes up, this can become a problematic task.

To solve this, you can use exclusive group rules:


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

# InDev Features
## todo Configurable class
## todo Option dependencies