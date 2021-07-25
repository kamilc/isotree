try:
    from setuptools import setup
    from setuptools.extension import Extension
except:
    from distutils.core import setup
    from distutils.extension import Extension

import numpy as np
from Cython.Distutils import build_ext
from sys import platform
import sys, os, subprocess, warnings, re
from os import environ

has_cereal = True
try:
    import cycereal
    cereal_dir = cycereal.get_cereal_include_dir()
except:
    has_cereal = False
    cereal_dir = "." ## <- placeholder


found_omp = True
def set_omp_false():
    global found_omp
    found_omp = False

## https://stackoverflow.com/questions/724664/python-distutils-how-to-get-a-compiler-that-is-going-to-be-used
class build_ext_subclass( build_ext ):
    def build_extensions(self):
        is_msvc = self.compiler.compiler_type == "msvc"
        is_clang = hasattr(self.compiler, 'compiler_cxx') and ("clang++" in self.compiler.compiler_cxx)

        if is_msvc:
            for e in self.extensions:
                e.extra_compile_args = ['/openmp', '/O2', '/std:c++14', '/wd4244', '/wd4267', '/wd4018']
                ### Note: MSVC never implemented C++11
        else:
            self.add_march_native()
            self.add_openmp_linkage()

            for e in self.extensions:
                if is_clang:
                    e.extra_compile_args += ['-O3', '-std=c++17']
                else:
                    e.extra_compile_args += ['-O3', '-std=c++11']

        # if is_clang:
        #     for e in self.extensions:
        #         e.extra_compile_args = ['-fopenmp', '-O3', '-march=native', '-std=c++17']
        #         # e.extra_link_args    = ['-fopenmp']
        #         # e.extra_link_args    = ['-fopenmp=libiomp5']
        #         e.extra_link_args    = ['-fopenmp=libomp']
        #         ### Note: when passing C++11 to CLANG, it complains about C++17 features in CYTHON_FALLTHROUGH
        # else: # gcc
        #     for e in self.extensions:
        #         e.extra_compile_args = ['-fopenmp', '-O3', '-march=native', '-std=c++11']
        #         e.extra_link_args    = ['-fopenmp']

                ### when testing with clang:
                # e.extra_compile_args = ['-fopenmp=libiomp5', '-O3', '-march=native', '-std=c++11']
                # e.extra_link_args    = ['-fopenmp=libiomp5']
                # e.extra_compile_args = ['-fopenmp=libiomp5', '-O2', '-march=native', '-std=c++11', '-stdlib=libc++', '-lc++abi']
                # e.extra_link_args    = ['-fopenmp=libiomp5', '-lc++abi']

                # e.extra_compile_args = ['-O2', '-march=native', '-std=c++11']
                # e.extra_compile_args = ['-O0', '-march=native', '-std=c++11']

                ### for testing (run with `LD_PRELOAD=libasan.so python script.py`)
                # e.extra_compile_args = ["-std=c++11", "-fsanitize=address", "-static-libasan", "-ggdb"]
                # e.extra_link_args    = ["-fsanitize=address", "-static-libasan"]

                ### when testing for oneself
                # e.extra_compile_args += ["-Wno-sign-compare", "-Wno-switch", "-Wno-maybe-uninitialized"]


        build_ext.build_extensions(self)

    def add_march_native(self):
        arg_march_native = "-march=native"
        arg_mcpu_native = "-mcpu=native"
        if self.test_supports_compile_arg(arg_march_native):
            for e in self.extensions:
                e.extra_compile_args.append(arg_march_native)
        elif self.test_supports_compile_arg(arg_mcpu_native):
            for e in self.extensions:
                e.extra_compile_args.append(arg_mcpu_native)

    def add_openmp_linkage(self):
        arg_omp1 = "-fopenmp"
        arg_omp2 = "-qopenmp"
        arg_omp3 = "-xopenmp"
        args_apple_omp = ["-Xclang", "-fopenmp", "-lomp"]
        if self.test_supports_compile_arg(arg_omp1):
            for e in self.extensions:
                e.extra_compile_args.append(arg_omp1)
                e.extra_link_args.append(arg_omp1)
        elif (sys.platform[:3].lower() == "dar") and self.test_supports_compile_arg(args_apple_omp):
            for e in self.extensions:
                e.extra_compile_args += ["-Xclang", "-fopenmp"]
                e.extra_link_args += ["-lomp"]
        elif self.test_supports_compile_arg(arg_omp2):
            for e in self.extensions:
                e.extra_compile_args.append(arg_omp2)
                e.extra_link_args.append(arg_omp2)
        elif self.test_supports_compile_arg(arg_omp3):
            for e in self.extensions:
                e.extra_compile_args.append(arg_omp3)
                e.extra_link_args.append(arg_omp3)
        else:
            set_omp_false()

    def test_supports_compile_arg(self, comm):
        is_supported = False
        try:
            if not hasattr(self.compiler, "compiler_cxx"):
                return False
            if not isinstance(comm, list):
                comm = [comm]
            print("--- Checking compiler support for option '%s'" % " ".join(comm))
            fname = "isotree_compiler_testing.cpp"
            with open(fname, "w") as ftest:
                ftest.write(u"int main(int argc, char**argv) {return 0;}\n")
            try:
                cmd = [self.compiler.compiler_cxx[0]]
            except:
                cmd = list(self.compiler.compiler_cxx)
            val_good = subprocess.call(cmd + [fname])
            try:
                val = subprocess.call(cmd + comm + [fname])
                is_supported = (val == val_good)
            except:
                is_supported = False
        except:
            pass
        try:
            os.remove(fname)
        except:
            pass
        return is_supported


setup(
    name  = "isotree",
    packages = ["isotree"],
    version = '0.3.0',
    description = 'Isolation-Based Outlier Detection, Distance, and NA imputation',
    author = 'David Cortes',
    author_email = 'david.cortes.rivera@gmail.com',
    url = 'https://github.com/david-cortes/isotree',
    keywords = ['isolation-forest', 'anomaly', 'outlier'],
    cmdclass = {'build_ext': build_ext_subclass},
    ext_modules = [Extension(
                                "isotree._cpp_interface",
                                sources=["isotree/cpp_interface.pyx",
                                         "src/merge_models.cpp", "src/serialize.cpp", "src/sql.cpp"],
                                include_dirs=[np.get_include(), ".", "./src", cereal_dir],
                                language="c++",
                                install_requires = ["numpy", "pandas>=0.24.0", "cython", "scipy"],
                                define_macros = [("_USE_XOSHIRO", None),
                                                 ("_ENABLE_CEREAL", None) if has_cereal else ("NO_CEREAL", None),
                                                 ("_USE_ROBIN_MAP", None),
                                                 ("_FOR_PYTHON", None),
                                                 ("PY_GEQ_3_3", None)
                                                 if (sys.version_info[0] >= 3 and sys.version_info[1] >= 3) else
                                                 ("PY_LT_3_3", None)]
                            )]
    )

if not found_omp:
    omp_msg  = "\n\n\nCould not detect OpenMP. Package will be built without multi-threading capabilities. "
    omp_msg += " To enable multi-threading, first install OpenMP"
    if (sys.platform[:3] == "dar"):
        omp_msg += " - for macOS: 'brew install libomp'\n"
    else:
        omp_msg += " modules for your compiler. "
    
    omp_msg += "Then reinstall this package from scratch: 'pip install --force-reinstall isotree'.\n"
    warnings.warn(omp_msg)


if not has_cereal:
    import warnings
    msg  = "\n\nWarning: cereal library not found. Package will be built "
    msg += "without serialization (importing/exporting models) capabilities. "
    msg += "In order to enable cereal, install package 'cycereal' and reinstall "
    msg += "'isotree' by downloading the source files and running "
    msg += "'python setup.py install'.\n"
    warnings.warn(msg)
