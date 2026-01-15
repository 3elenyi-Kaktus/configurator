import logging
from typing import Optional, TypeAlias

from configurator.option_name import IOptionName


class Depends:
    def __init__(self, *args: IOptionName):
        self.groups: list[tuple[IOptionName, ...]] = [tuple(option_name for option_name in args)]

    def __and__(self, other: "Depends") -> "Depends":
        result: list[tuple[IOptionName, ...]] = []
        for dependency_group in self.groups:
            for other_dependency_group in other.groups:
                result.append((*dependency_group, *other_dependency_group))
        self.groups = result
        return self

    def __or__(self, other: "Depends") -> "Depends":
        self.groups.extend(other.groups)
        return self


DependencyGroup: TypeAlias = list[IOptionName]


# TODO  This is a straightforward way to resolve all possible graphs by brute-forcing every
#       possible dependency edge combinations.
#       There may be a better way (i.e. recursion).


class OptionGraph:
    def __init__(self) -> None:
        self.nodes: set[IOptionName] = set()
        self.edges: dict[IOptionName, list[IOptionName]] = {}

    def addNode(self, name: IOptionName, children: list[IOptionName] = None) -> None:
        if name in self.nodes:
            raise RuntimeError(f"Node {name} already exists")
        self.nodes.add(name)
        self.edges[name] = []
        if children is not None:
            for child in children:
                self.addEdge(name, child)

    def addEdge(self, start: IOptionName, end: IOptionName) -> None:
        if start not in self.nodes:
            raise RuntimeError(f"Start node '{start}' doesn't exist")
        if end not in self.nodes:
            raise RuntimeError(f"End node '{end}' doesn't exist")

        paths: list[list[IOptionName]] = self.getPaths(end, start)
        self.edges[start].append(end)

        if paths is None:
            return
        raise RuntimeError(f"A cycle found between '{start}' and '{end}': {paths}")

    def getPaths(self, start: IOptionName, end: IOptionName) -> Optional[list[list[IOptionName]]]:
        if start == end:
            return [[end]]
        if not self.edges[start]:
            return None
        result: list[list[IOptionName]] = []
        for child in self.edges[start]:
            if (paths := self.getPaths(child, end)) is not None:
                for path in paths:
                    result.append([start, *path])
        if result:
            return result
        return None

    def collectDependencies(self, option_name: IOptionName) -> DependencyGroup:
        dependencies: DependencyGroup = []
        for child in self.edges[option_name]:
            dependencies.append(child)
            dependencies.extend(self.collectDependencies(child))
        return dependencies

    def getLongestPathLen(self) -> int:
        longest_path: int = 0
        for start_node in self.nodes:
            for end_node in self.nodes:
                paths: list[list[IOptionName]] = self.getPaths(start_node, end_node)
                if paths is None:
                    continue
                longest_path = max(longest_path, *[len(path) for path in paths])
        return longest_path


Edge: TypeAlias = tuple[IOptionName, IOptionName]


ExclusiveGroup: TypeAlias = tuple[IOptionName, ...]
ExclusiveGroupRule: TypeAlias = tuple[ExclusiveGroup, ...]


class DependenciesResolver:
    def __init__(
        self, option_raw_dependencies: dict[IOptionName, Depends], exclusive_group_rules: list[ExclusiveGroupRule]
    ):
        edge_combinations: list[list[Edge]] = self.createEdgeCombinations(option_raw_dependencies)
        self.graphs: list[OptionGraph] = []
        options: list[IOptionName] = [name for name in option_raw_dependencies.keys()]
        for combination in edge_combinations:
            self.graphs.append(self.buildGraph(options, combination, exclusive_group_rules))

    @staticmethod
    def createEdgeCombinations(option_raw_dependencies: dict[IOptionName, Depends]) -> list[list[Edge]]:
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

    @staticmethod
    def buildGraph(
        options: list[IOptionName], relations: list[Edge], exclusive_group_rules: list[ExclusiveGroupRule]
    ) -> OptionGraph:
        graph: OptionGraph = OptionGraph()
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

    def collectDependencies(self, option_name: IOptionName) -> list[DependencyGroup]:
        dependencies: list[DependencyGroup] = []
        for graph in self.graphs:
            dependencies.append(graph.collectDependencies(option_name))
        logging.info(f"Deps for {option_name}: {dependencies}")
        logging.info(f"\n\n")
        return dependencies
