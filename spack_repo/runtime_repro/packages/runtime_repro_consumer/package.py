import os

from spack_repo.builtin.build_systems.generic import Package

from spack.package import *


class RuntimeReproConsumer(Package):
    """C program linking Bzip2 and a tiny C++ library."""

    has_code = False
    version("1.0")
    depends_on("c", type="build")
    depends_on("bzip2@1.0.8+shared")
    depends_on("runtime-repro-modern@1.0")

    def install(self, spec, prefix):
        mkdirp(prefix.bin)
        Executable(spack_cc)(
            os.path.join(os.path.dirname(__file__), "main.c"),
            "-lruntime_repro_modern",
            "-lbz2",
            "-o",
            os.path.join(prefix.bin, "runtime-repro"),
        )
