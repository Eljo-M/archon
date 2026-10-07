"""Generate packaged Python stubs from the central service contract."""

from pathlib import Path

from grpc_tools import protoc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "archon" / "generated"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "__init__.py").write_text('"""Generated Protobuf service bindings."""\n', encoding="utf-8", newline="\n")
result = protoc.main(["grpc_tools.protoc", f"-I{ROOT / 'proto'}", f"--python_out={OUT}",
                      f"--grpc_python_out={OUT}", str(ROOT / "proto" / "archon.proto")])
if result:
    raise SystemExit(result)
stub = OUT / "archon_pb2_grpc.py"
stub.write_text(stub.read_text(encoding="utf-8").replace(
    "import archon_pb2 as archon__pb2", "from . import archon_pb2 as archon__pb2"), encoding="utf-8", newline="\n")
print(f"Generated stubs in {OUT}")
