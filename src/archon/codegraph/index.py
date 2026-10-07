import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import tree_sitter_python
from tree_sitter import Language, Parser

IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".archon"}


@dataclass(frozen=True)
class Symbol:
    path: str
    name: str
    kind: str
    start_line: int
    end_line: int


def safe_source_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if not relative or "\\" in relative or path.is_absolute() or ".." in path.parts or ":" in relative:
        raise ValueError("source path must be workspace-relative")
    candidate = root.joinpath(*path.parts)
    if any(part in IGNORED for part in path.parts) or candidate.suffix != ".py":
        raise ValueError("only Python source files are supported in the initial navigation engine")
    if candidate.is_symlink() or root.resolve() not in candidate.resolve().parents:
        raise ValueError("source escapes workspace")
    if not candidate.is_file() or candidate.stat().st_size > 128_000:
        raise ValueError("source does not exist or exceeds context size limit")
    return candidate


class CodeIndex:
    def __init__(self, root: Path):
        self.root = root
        self.parser = Parser(Language(tree_sitter_python.language()))
        self.symbols: list[Symbol] = []

    def build(self) -> list[Symbol]:
        self.symbols = []
        files = 0
        total_bytes = 0
        for candidate in sorted(self.root.rglob("*.py")):
            relative = candidate.relative_to(self.root).as_posix()
            if any(part in IGNORED for part in candidate.relative_to(self.root).parts):
                continue
            try:
                path = safe_source_path(self.root, relative)
            except ValueError:
                continue
            files += 1
            total_bytes += path.stat().st_size
            if files > 2000 or total_bytes > 16_000_000:
                raise ValueError("repository exceeds initial code index limits")
            source = path.read_bytes()
            tree = self.parser.parse(source)
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in {"function_definition", "class_definition"}:
                    name = node.child_by_field_name("name")
                    if name:
                        self.symbols.append(Symbol(relative, source[name.start_byte:name.end_byte].decode(),
                                                   node.type, node.start_point.row + 1, node.end_point.row + 1))
                stack.extend(reversed(node.children))
        return self.symbols

    def relevant(self, description: str, limit: int = 60) -> list[dict]:
        terms = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]+", description.lower()))
        ranked = sorted(self.symbols, key=lambda s: (
            -sum(word in f"{s.name} {s.path}".lower() for word in terms), s.path, s.start_line))
        return [asdict(symbol) for symbol in ranked[:limit]]

    def read_sources(self, paths: list[str], byte_budget: int = 48_000) -> dict[str, str]:
        if not paths or len(paths) > 8:
            raise ValueError("architect must choose between one and eight files")
        result = {}
        for relative in dict.fromkeys(paths):
            content = safe_source_path(self.root, relative).read_text(encoding="utf-8")
            byte_budget -= len(content.encode())
            if byte_budget < 0:
                raise ValueError("selected source context exceeds size limit")
            result[relative] = content
        return result
