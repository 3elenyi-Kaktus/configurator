from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from typing_extensions import Self

from kaktus.configurator.commons import OptionName
from kaktus.configurator.graph import DAG


if TYPE_CHECKING:
    from kaktus.configurator.option import Option


class Depends:
    def __init__(self, *args: Option):
        self.groups: list[tuple[OptionName, ...]] = [tuple(option.name for option in args)]

    def __and__(self, other: Self) -> Self:
        result: list[tuple[OptionName, ...]] = []
        for dependency_group in self.groups:
            for other_dependency_group in other.groups:
                result.append((*dependency_group, *other_dependency_group))
        self.groups = result
        return self

    def __or__(self, other: Self) -> Self:
        self.groups.extend(other.groups)
        return self


# TODO  This is a straightforward way to resolve all possible graphs by brute-forcing every
#       possible dependency edge combinations.
#       There may be a better way (i.e. recursion).


Edge: TypeAlias = tuple[OptionName, OptionName]
DependencyGroup: TypeAlias = list[OptionName]
ExclusiveGroup: TypeAlias = tuple[OptionName, ...]
ExclusiveGroupRule: TypeAlias = tuple[ExclusiveGroup, ...]


class DependenciesResolver:
    def __init__(self, images_dirpath: Path | None):
        self.images_dirpath: Path | None = images_dirpath

        self.graphs: list[DAG[OptionName]] = []

        if self.images_dirpath is None:
            return
        try:
            DAG.requireDrawing()
        except ImportError as exc:
            raise ImportError(
                "Drawing option graphs requires the 'graphs' extra. Install the 'kaktus-configurator[graphs]'"
            ) from exc
        self.images_dirpath.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        option_raw_dependencies: dict[OptionName, Depends | None],
        exclusive_group_rules: list[ExclusiveGroupRule],
    ) -> None:
        edge_combinations: list[list[Edge]] = self.createEdgeCombinations(option_raw_dependencies)
        options: list[OptionName] = [name for name in option_raw_dependencies.keys()]
        for combination in edge_combinations:
            self.graphs.append(self.buildGraph(options, combination))
        for graph in self.graphs:
            self.checkGraph(graph, options, exclusive_group_rules)

    @staticmethod
    def checkGraph(
        graph: DAG[OptionName], options: list[OptionName], exclusive_group_rules: list[ExclusiveGroupRule]
    ) -> None:
        for option in options:
            dependencies: DependencyGroup = graph.getDescendants(option)
            logging.info(f"Dependencies for option {option} local graph: {dependencies}")

            # Ugly, but I don't know a better way to do this
            for exclusive_group_rule in exclusive_group_rules:
                for i, group_a in enumerate(exclusive_group_rule):
                    for group_b in exclusive_group_rule[i + 1 :]:
                        for option_a in group_a:
                            for option_b in group_b:
                                if option_a in dependencies and option_b in dependencies:
                                    raise RuntimeError(
                                        f"Option {option} has mixed deps: {option_a, option_b} are exclusive"
                                    )

    @staticmethod
    def createEdgeCombinations(option_raw_dependencies: dict[OptionName, Depends | None]) -> list[list[Edge]]:
        edge_combinations: list[list[Edge]] = [[]]
        for option_name, raw_dependencies in option_raw_dependencies.items():
            logging.info(f"Adding option {option_name}")
            if raw_dependencies is None:
                logging.info("No deps")
                continue
            logging.info(f"Dependencies: {raw_dependencies.groups}")
            res = []
            logging.info("Many group")
            for group in raw_dependencies.groups:
                current = []
                for combination in edge_combinations:
                    current.append([*combination, *[(option_name, x) for x in group]])
                res.extend(current)
            edge_combinations = res
            logging.info(edge_combinations)
        return edge_combinations

    def buildGraph(self, options: list[OptionName], relations: list[Edge]) -> DAG[OptionName]:
        graph: DAG[OptionName] = DAG()
        for option in options:
            graph.addNode(option)
        for start, end in relations:
            try:
                graph.addEdge(start, end)
            except RuntimeError as exc:
                if self.images_dirpath is None:
                    logging.warning("Option graphs dirpath is not set. You should do it to get a visual reference")
                else:
                    graph.save(self.images_dirpath)
                raise RuntimeError("Failed to build the graph") from exc

        return graph

    def collectDependencies(self, option_name: OptionName) -> list[DependencyGroup]:
        dependencies: list[DependencyGroup] = []
        for graph in self.graphs:
            dependencies.append(graph.getDescendants(option_name))
        logging.info(f"Deps for {option_name}: {dependencies}")
        logging.info("\n\n")
        return dependencies
