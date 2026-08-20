from collections.abc import Hashable
import logging
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4


log: logging.Logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Hashable)


class DAG(Generic[T]):
    def __init__(self) -> None:
        self.nodes: set[T] = set()
        self.edges: dict[T, list[T]] = {}

    @classmethod
    def requireDrawing(cls) -> None:
        import importlib.util

        spec = importlib.util.find_spec("pygraphviz")
        if spec is None:
            raise ImportError("Saving graph images requires 'pygraphviz'")

    def addNode(self, node: T, children: list[T] | None = None) -> None:
        if node in self.nodes:
            raise RuntimeError(f"Node {node} already exists")
        self.nodes.add(node)
        self.edges[node] = []
        if children is not None:
            for child in children:
                self.addEdge(node, child)

    def addEdge(self, start: T, end: T) -> None:
        if start not in self.nodes:
            raise RuntimeError(f"Start node '{start}' doesn't exist")
        if end not in self.nodes:
            raise RuntimeError(f"End node '{end}' doesn't exist")

        paths: list[list[T]] | None = self.getPaths(end, start)
        if paths is not None:
            raise RuntimeError(f"A cycle found between '{start}' and '{end}': {paths}")

        self.edges[start].append(end)

    def getPaths(self, start: T, end: T) -> list[list[T]] | None:
        if start == end:
            return [[end]]
        if not self.edges[start]:
            return None
        result: list[list[T]] = []
        for child in self.edges[start]:
            if (paths := self.getPaths(child, end)) is not None:
                for path in paths:
                    result.append([start, *path])
        if result:
            return result
        return None

    def getDescendants(self, node: T) -> list[T]:
        descendants: list[T] = []
        for child in self.edges[node]:
            descendants.append(child)
            descendants.extend(self.getDescendants(child))
        return descendants

    def getLongestPathLen(self) -> int:
        longest_path: int = 0
        for start_node in self.nodes:
            for end_node in self.nodes:
                paths: list[list[T]] | None = self.getPaths(start_node, end_node)
                if paths is None:
                    continue
                longest_path = max(longest_path, *[len(path) for path in paths])
        return longest_path

    def save(self, dirpath: Path, fname: str | None = None) -> Path:
        from pygraphviz import AGraph  # type: ignore[import-untyped]

        graph = AGraph(strict=False, directed=True)
        graph.node_attr["color"] = "lightblue2"
        graph.node_attr["style"] = "filled"

        for node in self.nodes:
            graph.add_node(node)
            for child in self.edges[node]:
                graph.add_edge(node, child)

        max_path_len: int = self.getLongestPathLen()
        graph.unflatten(f"-f -l 3 -c {max_path_len}")
        graph.layout(prog="dot")

        if fname is None:
            fname = f"{uuid4()}.png"
        fpath: Path = dirpath / fname
        graph.draw(fpath)
        log.info(f"Saved graph image to '{fpath}'")
        return fpath
