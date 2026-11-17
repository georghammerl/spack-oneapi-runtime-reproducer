import os

from spack_repo.builtin.build_systems.generic import Package

from spack.package import *


class RuntimeReproModern(Package):
    """Tiny C++ library using the C++ standard library."""

    has_code = False
    version("1.0")
    depends_on("cxx", type="build")

    def install(self, spec, prefix):
        mkdirp(prefix.lib)
        Executable(spack_cxx)(
            "-std=c++17",
            "-fPIC",
            "-shared",
            os.path.join(os.path.dirname(__file__), "library.cpp"),
            "-Wl,-soname,libruntime_repro_modern.so",
            "-o",
            os.path.join(prefix.lib, "libruntime_repro_modern.so"),
        )
