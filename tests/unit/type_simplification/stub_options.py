"""Minimal loadable module for Generator fixtures (empty option group list)."""

from __future__ import annotations

from kaktus.configurator.option_group import OptionGroup


option_groups: list[type[OptionGroup]] = []
