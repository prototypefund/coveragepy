# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""Tests for coverage.execfile"""

import compileall
import json
import os
import os.path
import pathlib
import re

import pytest

from coverage import env
from coverage.exceptions import NoCode, NoSource
from coverage.execfile import run_python_file, run_python_module
from coverage.files import python_reported_file

from tests.coveragetest import CoverageTest, TESTS_DIR, UsingModulesMixin

TRY_EXECFILE = os.path.join(TESTS_DIR, "modules/process_test/try_execfile.py")


class RunFileTest(CoverageTest):
    """Test cases for `run_python_file`."""

    def test_run_python_file(self):
        run_python_file([TRY_EXECFILE, "arg1", "arg2"])
        mod_globs = json.loads(self.stdout())

        # The file should think it is __main__
        assert mod_globs['__name__'] == "__main__"

        # It should seem to come from a file named try_execfile.py
        dunder_file = os.path.basename(mod_globs['__file__'])
        assert dunder_file == "try_execfile.py"

        # It should have its correct module data.
        assert mod_globs['__doc__'].splitlines()[0] == "Test file for run_python_file."
        assert mod_globs['DATA'] == "xyzzy"
        assert mod_globs['FN_VAL'] == "my_fn('fooey')"

        # It must be self-importable as __main__.
        assert mod_globs['__main__.DATA'] == "xyzzy"

        # Argv should have the proper values.
        assert mod_globs['argv0'] == TRY_EXECFILE
        assert mod_globs['argv1-n'] == ["arg1", "arg2"]

        # __builtins__ should have the right values, like open().
        assert mod_globs['__builtins__.has_open'] is True

    def test_no_extra_file(self):
        # Make sure that running a file doesn't create an extra compiled file.
        self.make_file("xxx", """\
            desc = "a non-.py file!"
            """)

        assert os.listdir(".") == ["xxx"]
        run_python_file(["xxx"])
        assert os.listdir(".") == ["xxx"]

    def test_universal_newlines(self):
        # Make sure we can read any sort of line ending.
        pylines = """# try newlines|print('Hello, world!')|""".split('|')
        for nl in ('\n', '\r\n', '\r'):
            with open('nl.py', 'wb') as fpy:
                fpy.write(nl.join(pylines).encode('utf-8'))
            run_python_file(['nl.py'])
        assert self.stdout() == "Hello, world!\n"*3

    def test_missing_final_newline(self):
        # Make sure we can deal with a Python file with no final newline.
        self.make_file("abrupt.py", """\
            if 1:
                a = 1
                print("a is %r" % a)
                #""")
        with open("abrupt.py") as f:
            abrupt = f.read()
        assert abrupt[-1] == '#'
        run_python_file(["abrupt.py"])
        assert self.stdout() == "a is 1\n"

    def test_no_such_file(self):
        path = python_reported_file('xyzzy.py')
        msg = re.escape(f"No file to run: '{path}'")
        with pytest.raises(NoSource, match=msg):
            run_python_file(["xyzzy.py"])

    def test_directory_with_main(self):
        self.make_file("with_main/__main__.py", """\
            print("I am __main__")
            """)
        run_python_file(["with_main"])
        assert self.stdout() == "I am __main__\n"

    def test_directory_without_main(self):
        self.make_file("without_main/__init__.py", "")
        with pytest.raises(NoSource, match="Can't find '__main__' module in 'without_main'"):
            run_python_file(["without_main"])


class RunPycFileTest(CoverageTest):
    """Test cases for `run_python_file`."""

    def make_pyc(self):
        """Create a .pyc file, and return the path to it."""
        if env.JYTHON:
            pytest.skip("Can't make .pyc files on Jython")

        self.make_file("compiled.py", """\
            def doit():
                print("I am here!")

            doit()
            """)
        compileall.compile_dir(".", quiet=True)
        os.remove("compiled.py")

        # Find the .pyc file!
        return str(next(pathlib.Path(".").rglob("compiled*.pyc")))

    def test_running_pyc(self):
        pycfile = self.make_pyc()
        run_python_file([pycfile])
        assert self.stdout() == "I am here!\n"

    def test_running_pyo(self):
        pycfile = self.make_pyc()
        pyofile = re.sub(r"[.]pyc$", ".pyo", pycfile)
        assert pycfile != pyofile
        os.rename(pycfile, pyofile)
        run_python_file([pyofile])
        assert self.stdout() == "I am here!\n"

    def test_running_pyc_from_wrong_python(self):
        pycfile = self.make_pyc()

        # Jam Python 2.1 magic number into the .pyc file.
        with open(pycfile, "r+b") as fpyc:
            fpyc.seek(0)
            fpyc.write(bytes([0x2a, 0xeb, 0x0d, 0x0a]))

        with pytest.raises(NoCode, match="Bad magic number in .pyc file"):
            run_python_file([pycfile])

        # In some environments, the pycfile persists and pollutes another test.
        os.remove(pycfile)

    def test_no_such_pyc_file(self):
        path = python_reported_file('xyzzy.pyc')
        msg = re.escape(f"No file to run: '{path}'")
        with pytest.raises(NoCode, match=msg):
            run_python_file(["xyzzy.pyc"])

    def test_running_py_from_binary(self):
        # Use make_file to get the bookkeeping. Ideally, it would
        # be able to write binary files.
        bf = self.make_file("binary")
        with open(bf, "wb") as f:
            f.write(b'\x7fELF\x02\x01\x01\x00\x00\x00')

        path = python_reported_file('binary')
        msg = (
            re.escape(f"Couldn't run '{path}' as Python code: ") +
            r"(TypeError|ValueError): "
            r"("
            r"compile\(\) expected string without null bytes"    # for py2
            r"|"
            r"source code string cannot contain null bytes"     # for py3
            r")"
        )
        with pytest.raises(Exception, match=msg):
            run_python_file([bf])


class RunModuleTest(UsingModulesMixin, CoverageTest):
    """Test run_python_module."""

    run_in_temp_dir = False

    def test_runmod1(self):
        run_python_module(["runmod1", "hello"])
        out, err = self.stdouterr()
        assert out == "runmod1: passed hello\n"
        assert err == ""

    def test_runmod2(self):
        run_python_module(["pkg1.runmod2", "hello"])
        out, err = self.stdouterr()
        assert out == "pkg1.__init__: pkg1\nrunmod2: passed hello\n"
        assert err == ""

    def test_runmod3(self):
        run_python_module(["pkg1.sub.runmod3", "hello"])
        out, err = self.stdouterr()
        assert out == "pkg1.__init__: pkg1\nrunmod3: passed hello\n"
        assert err == ""

    def test_pkg1_main(self):
        run_python_module(["pkg1", "hello"])
        out, err = self.stdouterr()
        assert out == "pkg1.__init__: pkg1\npkg1.__main__: passed hello\n"
        assert err == ""

    def test_pkg1_sub_main(self):
        run_python_module(["pkg1.sub", "hello"])
        out, err = self.stdouterr()
        assert out == "pkg1.__init__: pkg1\npkg1.sub.__main__: passed hello\n"
        assert err == ""

    def test_pkg1_init(self):
        run_python_module(["pkg1.__init__", "wut?"])
        out, err = self.stdouterr()
        assert out == "pkg1.__init__: pkg1\npkg1.__init__: __main__\n"
        assert err == ""

    def test_no_such_module(self):
        with pytest.raises(NoSource, match="No module named '?i_dont_exist'?"):
            run_python_module(["i_dont_exist"])
        with pytest.raises(NoSource, match="No module named '?i'?"):
            run_python_module(["i.dont_exist"])
        with pytest.raises(NoSource, match="No module named '?i'?"):
            run_python_module(["i.dont.exist"])

    def test_no_main(self):
        with pytest.raises(NoSource):
            run_python_module(["pkg2", "hi"])
