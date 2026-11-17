import os

from spack_repo.builtin.build_systems.generic import Package

from spack.package import *


class RuntimeReproConsumer(Package):
    """C executable linking a cached C library and a newly built C++ library."""

    has_code = False
    version("1.0")
    depends_on("c", type="build")
    depends_on("bzip2@1.0.8+shared")
    depends_on("runtime-repro-modern@1.0")

    def install(self, spec, prefix):
        mkdirp(prefix.bin)
        modern = spec["runtime-repro-modern"].prefix.lib
        legacy = spec["bzip2"].prefix.lib
        for name in sorted(os.environ):
            if name.startswith("SPACK_") and any(
                token in name
                for token in ("LINK_DIRS", "RPATH_DIRS", "CC", "TARGET_ARGS")
            ):
                print(f"{name}={os.environ[name]}", flush=True)
        Executable(spack_cc)(
            os.path.join(os.path.dirname(__file__), "main.c"),
            f"-L{modern}",
            "-lruntime_repro_modern",
            f"-L{legacy}",
            "-lbz2",
            f"-Wl,-rpath,{modern}",
            "-Wl,-t",
            "-Wl,--trace-symbol=_ZSt21ios_base_library_initv",
            "-o",
            os.path.join(prefix.bin, "runtime-repro"),
        )
