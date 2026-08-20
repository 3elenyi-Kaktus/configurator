# InDev Features

#### Add method to base argparser which automatically suppresses arguments if they were not supplied (argparse.SUPPRESS)
#### Imports in \_\_all__
#### Check for duplicate options (use sets) in dependencies and exclusive groups
#### Do we really need Depends or these operators can be safely overloaded in optionName enum?
#### Do we need any other types (apart from int and str) in .env files?
#### Configurable class
#### Tests for invariants

#### Write or fix: system options are not changeable from the runtime (they dont have any setters). Also make changes from runtime to reload the config (trigger the callbacks)
#### Refactor Option in_type/rtype fields typing (make it safer and properly typed, instead of loosely attaching `type`)
#### Make Option generic (`Option[I, R]`); type `_getOptionValue` / `_setOptionValue`; annotate option class attributes (or add a factory) so generated proxy getters typecheck without `no-any-return`
#### Fix typing of `optionGroup` decorator (most possibly split into 2 different overloaded functions, so that return types are not unionized)
