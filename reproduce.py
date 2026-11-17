#!/usr/bin/env python3
"""Run an isolated Spack experiment, or smoke-test the two source projects natively."""

import argparse
import ctypes.util
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEGACY_HASH = "uvnzqyaxcaq5r3l6mh46yow7dfbp5fnp"
ONEAPI = "2025.3.2"
SOURCES = ROOT / "spack_repo/runtime_repro/packages"


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def run(command, output, env=None, check=True):
    command = list(map(str, command))
    print("$", shlex.join(command), flush=True)
    with (output / "commands.log").open("a") as log:
        log.write("\n$ " + shlex.join(command) + "\n")
        log.flush()
        result = subprocess.run(
            command, env=env, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    print(f"Exit {result.returncode}; log: {output / 'commands.log'}", flush=True)
    if check:
        result.check_returncode()
    return result.returncode


def native_smoke(args, output):
    library = ctypes.util.find_library("bz2")
    if library is None:
        raise RuntimeError(
            "The native smoke test needs the system Bzip2 shared library"
        )
    run(
        [
            args.cxx,
            "-std=c++17",
            "-fPIC",
            "-shared",
            SOURCES / "runtime_repro_modern/library.cpp",
            "-Wl,-soname,libruntime_repro_modern.so",
            "-o",
            output / "libruntime_repro_modern.so",
        ],
        output,
    )
    run(
        [
            args.cc,
            SOURCES / "runtime_repro_consumer/main.c",
            f"-L{output}",
            "-lruntime_repro_modern",
            f"-Wl,-l:{library}",
            f"-Wl,-rpath,{output}",
            "-o",
            output / "runtime-repro",
        ],
        output,
    )
    run(["readelf", "-d", output / "libruntime_repro_modern.so"], output)
    run(["ldd", output / "runtime-repro"], output)
    run([output / "runtime-repro"], output)
    write_json(output / "result.json", {"mode": "native-smoke", "exit_code": 0})


def experiment(args, output):
    gcc = Path(shutil.which(args.gcc) or args.gcc).absolute()
    if not gcc.is_file() or not gcc.name.startswith("gcc"):
        raise RuntimeError(f"Expected an installed GCC executable, got {gcc}")
    suffix = gcc.name[3:]
    cxx, fortran = gcc.with_name("g++" + suffix), gcc.with_name("gfortran" + suffix)
    for path in (cxx, fortran):
        if not path.is_file():
            raise RuntimeError(f"Matching GCC C++/Fortran compiler is missing: {path}")
    gcc_version = subprocess.check_output([gcc, "-dumpfullversion"], text=True).strip()
    if int(gcc_version.split(".")[0]) < 13:
        raise RuntimeError(
            "Use GCC >=13 so its C++ runtime differs from the cached GCC 10 runtime"
        )
    spack = args.spack.resolve() / "bin/spack"
    builtin = args.packages.resolve() / "repos/spack_repo/builtin"
    if not spack.is_file() or not (builtin / "repo.yaml").is_file():
        raise RuntimeError(
            "--spack and --packages must point to existing source checkouts"
        )

    config = output / "config"
    config.mkdir()
    write_json(
        config / "repos.yaml",
        {
            "repos": {
                "runtime_repro": str(ROOT / "spack_repo/runtime_repro"),
                "builtin": str(builtin),
            }
        },
    )
    write_json(
        config / "config.yaml",
        {
            "config": {
                "install_tree": {"root": str(output / "store")},
                "build_stage": [str(output / "stage")],
                "source_cache": str(output / "sources"),
                "misc_cache": str(output / "cache"),
            }
        },
    )
    write_json(
        config / "bootstrap.yaml", {"bootstrap": {"root": str(output / "bootstrap")}}
    )
    write_json(
        config / "packages.yaml",
        {
            "packages": {
                "gcc": {
                    "buildable": False,
                    "externals": [
                        {
                            "spec": f"gcc@{gcc_version} languages=c,c++,fortran",
                            "prefix": str(gcc.parent.parent),
                            "extra_attributes": {
                                "compilers": {
                                    "c": str(gcc),
                                    "cxx": str(cxx),
                                    "fortran": str(fortran),
                                }
                            },
                        }
                    ],
                },
                "gcc-runtime": {"require": f"@{gcc_version}:"},
                "bzip2": {"require": f"/{LEGACY_HASH}"},
                "runtime-repro-modern": {"require": f"%cxx=oneapi@{ONEAPI}"},
            }
        },
    )
    write_json(
        config / "mirrors.yaml",
        {
            "mirrors": {
                "github-actions-buildcache": {
                    "url": "oci://ghcr.io/spack/github-actions-buildcache",
                    "signed": False,
                }
            }
        },
    )
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("SPACK_")
    }
    env.update(
        {
            "SPACK_DISABLE_LOCAL_CONFIG": "1",
            "SPACK_USER_CACHE_PATH": str(output / "user-cache"),
        }
    )
    command = [spack, "-C", config]
    run(["git", "-C", args.spack, "rev-parse", "HEAD"], output)
    run(["git", "-C", args.packages, "rev-parse", "HEAD"], output)
    run(command + ["--version"], output, env)
    # Do not silently rebuild the legacy binary with a missing GCC 10 compiler.
    run(
        command
        + ["install", "--fail-fast", "--use-buildcache", "only", f"/{LEGACY_HASH}"],
        output,
        env,
    )
    run(
        command
        + [
            "install",
            "--fail-fast",
            "--verbose",
            f"intel-oneapi-compilers@{ONEAPI}",
            f"%gcc@{gcc_version}",
        ],
        output,
        env,
    )

    environment = output / "environment"
    environment.mkdir()
    write_json(
        environment / "spack.yaml",
        {
            "spack": {
                "specs": [
                    f"runtime_repro.runtime-repro-consumer@1.0 %c=oneapi@{ONEAPI}"
                ],
                "view": False,
            }
        },
    )
    command += ["-e", environment]
    run(command + ["concretize"], output, env)
    run(command + ["spec", "-l"], output, env)
    run(
        command
        + [
            "install",
            "--only",
            "dependencies",
            "--fail-fast",
            "--verbose",
            "--show-log-on-error",
        ],
        output,
        env,
    )
    run(command + ["python", ROOT / "diagnose.py"], output, env)
    code = run(
        command
        + [
            "install",
            "--fail-fast",
            "--verbose",
            "--show-log-on-error",
            "--use-buildcache",
            "package:never,dependencies:auto",
        ],
        output,
        env,
        check=False,
    )
    phase = "consumer-link"
    if code == 0:
        phase = "consumer-execution"
        script = (
            "import subprocess; from spack.active_environment import active_environment; "
            "root,=active_environment().concrete_roots(); "
            'subprocess.run(["readelf","-d",str(root.prefix.bin)+"/runtime-repro"],check=True); '
            'subprocess.run(["ldd",str(root.prefix.bin)+"/runtime-repro"],check=True); '
            'subprocess.run([str(root.prefix.bin)+"/runtime-repro"],check=True)'
        )
        code = run(command + ["python", "-c", script], output, env, check=False)
    write_json(
        output / "result.json", {"mode": "spack", "phase": phase, "exit_code": code}
    )
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for all results"
    )
    parser.add_argument(
        "--native-smoke", action="store_true", help="Check sources, not the Spack bug"
    )
    parser.add_argument("--cc", default="cc", help="Native-smoke C compiler")
    parser.add_argument("--cxx", default="c++", help="Native-smoke C++ compiler")
    parser.add_argument("--spack", type=Path, help="Spack checkout; never modified")
    parser.add_argument(
        "--packages", type=Path, help="spack-packages checkout; never modified"
    )
    parser.add_argument(
        "--gcc", default="gcc-13", help="Installed GCC >=13, with matching G++/Fortran"
    )
    args = parser.parse_args()
    if not args.native_smoke and (args.spack is None or args.packages is None):
        parser.error(
            "--spack and --packages are required unless --native-smoke is selected"
        )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        if args.native_smoke:
            native_smoke(args, output)
            return 0
        return experiment(args, output)
    except subprocess.CalledProcessError as error:
        write_json(
            output / "result.json",
            {
                "mode": "native-smoke" if args.native_smoke else "spack",
                "phase": "setup-or-dependency",
                "command": list(map(str, error.cmd)),
                "exit_code": error.returncode,
            },
        )
        print(
            f"Command failed; inspect {output / 'commands.log'}. This is not a confirmed reproduction."
        )
        return error.returncode


if __name__ == "__main__":
    raise SystemExit(main())
