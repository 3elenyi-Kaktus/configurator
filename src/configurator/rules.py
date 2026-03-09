from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TypeAlias
from uuid import uuid4

from pygraphviz import AGraph

from configurator.commons import OptionName


if TYPE_CHECKING:
    from configurator.option import Option


class Depends:
    def __init__(self, *args: Option):
        self.groups: list[tuple[OptionName, ...]] = [tuple(option.name for option in args)]

    def __and__(self, other: "Depends") -> "Depends":
        result: list[tuple[OptionName, ...]] = []
        for dependency_group in self.groups:
            for other_dependency_group in other.groups:
                result.append((*dependency_group, *other_dependency_group))
        self.groups = result
        return self

    def __or__(self, other: "Depends") -> "Depends":
        self.groups.extend(other.groups)
        return self


DependencyGroup: TypeAlias = list[OptionName]


# TODO  This is a straightforward way to resolve all possible graphs by brute-forcing every
#       possible dependency edge combinations.
#       There may be a better way (i.e. recursion).


class OptionGraph:
    def __init__(self, graphs_dirpath: Optional[Path]) -> None:
        self.graphs_dirpath: Optional[Path] = graphs_dirpath
        if self.graphs_dirpath is not None and not self.graphs_dirpath.is_dir():
            self.graphs_dirpath.mkdir(parents=True, exist_ok=True)
        self.nodes: set[OptionName] = set()
        self.edges: dict[OptionName, list[OptionName]] = {}

    def addNode(self, name: OptionName, children: Optional[list[OptionName]] = None) -> None:
        if name in self.nodes:
            raise RuntimeError(f"Node {name} already exists")
        self.nodes.add(name)
        self.edges[name] = []
        if children is not None:
            for child in children:
                self.addEdge(name, child)

    def addEdge(self, start: OptionName, end: OptionName) -> None:
        if start not in self.nodes:
            raise RuntimeError(f"Start node '{start}' doesn't exist")
        if end not in self.nodes:
            raise RuntimeError(f"End node '{end}' doesn't exist")

        paths: Optional[list[list[OptionName]]] = self.getPaths(end, start)
        if paths is not None:
            if self.graphs_dirpath is None:
                logging.warning(f"Option graphs dirpath is not set. You should set it to get a visual reference")
            else:
                self.saveGraph()
            raise RuntimeError(f"A cycle found between '{start}' and '{end}': {paths}")

        self.edges[start].append(end)

    def getPaths(self, start: OptionName, end: OptionName) -> Optional[list[list[OptionName]]]:
        if start == end:
            return [[end]]
        if not self.edges[start]:
            return None
        result: list[list[OptionName]] = []
        for child in self.edges[start]:
            if (paths := self.getPaths(child, end)) is not None:
                for path in paths:
                    result.append([start, *path])
        if result:
            return result
        return None

    def collectDependencies(self, option_name: OptionName) -> DependencyGroup:
        dependencies: DependencyGroup = []
        for child in self.edges[option_name]:
            dependencies.append(child)
            dependencies.extend(self.collectDependencies(child))
        return dependencies

    def getLongestPathLen(self) -> int:
        longest_path: int = 0
        for start_node in self.nodes:
            for end_node in self.nodes:
                paths: Optional[list[list[OptionName]]] = self.getPaths(start_node, end_node)
                if paths is None:
                    continue
                longest_path = max(longest_path, *[len(path) for path in paths])
        return longest_path

    def saveGraph(self) -> None:
        graph: AGraph = AGraph(strict=False, directed=True)
        graph.node_attr["color"] = "lightblue2"
        graph.node_attr["style"] = "filled"

        for node_name in self.nodes:
            graph.add_node(node_name)
            for child in self.edges[node_name]:
                graph.add_edge(node_name, child)

        max_path_len: int = self.getLongestPathLen()
        graph.unflatten(f"-f -l 3 -c {max_path_len}")
        graph.layout(prog="dot")  # defaults to neato
        graph.draw(f"{uuid4()}.png")


Edge: TypeAlias = tuple[OptionName, OptionName]


ExclusiveGroup: TypeAlias = tuple[OptionName, ...]
ExclusiveGroupRule: TypeAlias = tuple[ExclusiveGroup, ...]


class DependenciesResolver:
    def __init__(
        self,
        option_graphs_dirpath: Optional[Path],
        option_raw_dependencies: dict[OptionName, Depends],
        exclusive_group_rules: list[ExclusiveGroupRule],
    ):
        self.option_graphs_dirpath: Optional[Path] = option_graphs_dirpath
        edge_combinations: list[list[Edge]] = self.createEdgeCombinations(option_raw_dependencies)
        self.graphs: list[OptionGraph] = []
        options: list[OptionName] = [name for name in option_raw_dependencies.keys()]
        for combination in edge_combinations:
            self.graphs.append(self.buildGraph(options, combination, exclusive_group_rules))

    @staticmethod
    def createEdgeCombinations(option_raw_dependencies: dict[OptionName, Depends]) -> list[list[Edge]]:
        edge_combinations: list[list[Edge]] = [[]]
        for option_name, raw_dependencies in option_raw_dependencies.items():
            logging.info(f"Adding option {option_name}")
            if raw_dependencies is None:
                logging.info(f"No deps")
                continue
            logging.info(f"Dependencies: {raw_dependencies.groups}")
            res = []
            logging.info(f"Many group")
            for group in raw_dependencies.groups:
                current = []
                for combination in edge_combinations:
                    current.append([*combination, *[(option_name, x) for x in group]])
                res.extend(current)
            edge_combinations = res
            logging.info(edge_combinations)
        return edge_combinations

    def buildGraph(
        self, options: list[OptionName], relations: list[Edge], exclusive_group_rules: list[ExclusiveGroupRule]
    ) -> OptionGraph:
        graph: OptionGraph = OptionGraph(self.option_graphs_dirpath)
        for option in options:
            graph.addNode(option)
        for edge in relations:
            graph.addEdge(*edge)

        for option in options:
            dependencies: DependencyGroup = graph.collectDependencies(option)
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
        return graph

    def collectDependencies(self, option_name: OptionName) -> list[DependencyGroup]:
        dependencies: list[DependencyGroup] = []
        for graph in self.graphs:
            dependencies.append(graph.collectDependencies(option_name))
        logging.info(f"Deps for {option_name}: {dependencies}")
        logging.info(f"\n\n")
        return dependencies
