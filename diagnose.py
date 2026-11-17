"""Run with `spack -e ENV python diagnose.py` after installing the dependencies."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import spack.build_environment
import spack.deptypes as dt
from spack.active_environment import active_environment
from spack.error import SpackError
from spack.util.environment import EnvironmentModifications


def command(*args):
    print("\n$", *map(str, args), flush=True)
    subprocess.run(list(map(str, args)), check=True)


environment = active_environment()
if environment is None:
    raise SpackError("Activate the experiment's environment with spack -e ENV")
(root,) = environment.concrete_roots()
runtimes = [
    node for node in root.traverse(deptype=dt.LINK) if node.name == "gcc-runtime"
]
if not any(node.satisfies("@10") for node in runtimes) or not any(
    node.satisfies("@13:") for node in runtimes
):
    raise SpackError(
        "Expected distinct GCC 10 and GCC >=13 link runtimes; experiment is unsuitable"
    )

print("Concrete link graph and name-based lookup:", flush=True)
for node in root.traverse(deptype=dt.LINK):
    selected = root[node.name] if node is not root else root
    print(
        f"{node.name}@{node.version}/{node.dag_hash()}: "
        f"lookup=/{selected.dag_hash()} same_node={node is selected} prefix={node.prefix}",
        flush=True,
    )

modifications = EnvironmentModifications()
spack.build_environment.set_wrapper_variables(root.package, modifications)
wrapper = {}
modifications.apply_modifications(wrapper)
for name in sorted(wrapper):
    if "LINK_DIRS" in name or "RPATH_DIRS" in name:
        print(f"{name}={wrapper[name]}", flush=True)
link_dirs = set(
    wrapper.get("SPACK_LINK_DIRS", "").split(os.pathsep)
    + wrapper.get("SPACK_STORE_LINK_DIRS", "").split(os.pathsep)
)
coverage = {
    f"{node.version}/{node.dag_hash()}": str(node.prefix.lib) in link_dirs
    for node in runtimes
}
print("Runtime directory coverage:", json.dumps(coverage, indent=2), flush=True)

compiler = root["c"].package
for executable in (compiler.cc, compiler.cxx):
    command(executable, "--version")
    command(executable, "-print-file-name=libstdc++.so")
    command(executable, "-print-file-name=libstdc++.so.6")
    cfg = Path(str(executable) + ".cfg")
    if cfg.is_file():
        print(f"{cfg}:\n{cfg.read_text()}", flush=True)

compiler_runtime = Path(
    subprocess.check_output(
        [compiler.cxx, "-print-file-name=libstdc++.so.6"], text=True
    ).strip()
)
if not compiler_runtime.is_file():
    raise SpackError(f"The C++ compiler did not locate its runtime: {compiler_runtime}")
compiler_runtime_hash = hashlib.sha256(compiler_runtime.read_bytes()).hexdigest()
print(f"Compiler-selected runtime SHA256: {compiler_runtime_hash}", flush=True)

source = (
    Path(__file__).parent
    / "spack_repo/runtime_repro/packages/runtime_repro_modern/library.cpp"
)
command(
    compiler.cxx, "-###", "-std=c++17", "-shared", "-fPIC", source, "-o", "/dev/null"
)
modern = Path(root["runtime-repro-modern"].prefix.lib) / "libruntime_repro_modern.so"
command("readelf", "-d", modern)
command("ldd", modern)
symbols = subprocess.check_output(
    ["readelf", "--dyn-syms", "--wide", str(modern)], text=True
)
print("\nC++ library's versioned undefined symbols:", flush=True)
for line in symbols.splitlines():
    if "UND" in line and ("GLIBCXX_" in line or "CXXABI_" in line):
        print(line, flush=True)
for node in runtimes:
    directory = Path(node.prefix.lib)
    print(
        f"\n{node.name}@{node.version}: {[p.name for p in directory.glob('libstdc++*')]}"
    )
    library = directory / "libstdc++.so.6"
    runtime_hash = hashlib.sha256(library.read_bytes()).hexdigest()
    print(
        f"SHA256={runtime_hash} matches_compiler={runtime_hash == compiler_runtime_hash}",
        flush=True,
    )
    symbols = subprocess.check_output(
        ["readelf", "--dyn-syms", "--wide", str(library)], text=True
    )
    definitions = [
        line
        for line in symbols.splitlines()
        if "ios_base_library_init" in line and "UND" not in line
    ]
    print("ios_base_library_init definitions:", definitions, flush=True)
