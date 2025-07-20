# Configurator base

### by 3elenyi Kaktus

Holds minimal base options for project configuration. Both config class and argument parser can be inherited and overloaded to provide extended flexibility.

## Internal logic

Base config options are injected into base config class as system options and shouldn't be overrun.
These are: path to config file, from which all options are retrieved and path to .env file with analogical purpose.

Strictly speaking, config file and .env file hold the exactly same purpose, with .env file functionality added for security reasons (holding sensitive information, such as passwords, which mustn't be published in open sources).

Argument sources have a strict priority over each one: $$cmd\ args \gt file\ args \gt\ .env\ args$$
If any of arguments is redeclared in another source, only the one with the highest source priority will be used.

Config supports hot reloading, polling for changes in provided config file if needed.
To leverage this functionality, config must be provided with list of objects, which rely on this feature.
On the other hand, every of these objects must support interface, described in config base class.
Due to design, arguments passed via command line can't be changed in runtime.

## Usage concept

Any custom added options to config should be proposed in following way.
Firstly, their names must be declared in enum class, inheriting from IOptionName base class.
Secondly, every option must be registered by adding expected types and validation functions for it.
Basic value validation just forwards value through implementation without any modifications.
