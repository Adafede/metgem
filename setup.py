import glob
import sys
import os

from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from distutils import cmd

import versioneer

# Gather data files
package_data = {'metgem_app': ['splash.png',
                               'styles/*.css',
                               'ui/widgets/images/*',
                               'ui/widgets/spectrum/images/*',
                               'models/*.csv',
                               ]}

data_files = [("", ["LICENSE"])]
if not sys.platform.startswith('darwin'):
    data_files.extend([('examples', ['examples/Codiaeum.csv', 'examples/Codiaeum.mgf',
                                     'examples/Stillingia SFE.csv', 'examples/Stillingia SFE.mgf',
                                     'examples/Stillingia group mapping.txt'])])


class ProcessResourceCommand(cmd.Command):
    """A custom command to compile the resource file into a Python file"""

    description = "Compile the qrc file into a python file"

    def initialize_options(self):
        return

    def finalize_options(self):
        return

    def run(self):
        qrcs = [os.path.join('metgem_app', 'ui', 'ui.qrc')]
        rc = os.path.join('metgem_app', 'ui', 'ui_rc.py')
        skip = False
        if os.path.exists(rc):
            rc_mtime = os.path.getmtime(rc)
            skip = not any([os.path.getmtime(qrc) > rc_mtime for qrc in qrcs])

        if not skip:
            os.system(f"pyside2-rcc -o {rc} {' '.join(qrcs)}")


class ProcessUICommand(cmd.Command):
    """A custom command to compile UI files into Python files"""

    description = "Compile ui files into python files"

    def initialize_options(self):
        return

    def finalize_options(self):
        return

    def run(self):
        for fn in glob.glob(os.path.join('metgem_app', 'ui', '**', '*.ui'), recursive=True):
            fn = os.path.realpath(fn)
            out = fn[:-3] + '_ui.py'
            os.system(f"pyside2-uic {fn} -o {out} ")


class BuildPyCommand(build_py):
    """Custom build command to include ProcessResource and ProcessUI commands"""

    def run(self):
        self.run_command("process_resource")
        self.run_command("process_ui")
        build_py.run(self)


setup(
    name='metgem',
    version=versioneer.get_version(),
    author="Nicolas Elie",
    author_email="nicolas.elie@cnrs.fr",
    url="https://github.com/metgem/metgem",
    description="Calculation and visualization of molecular networks based on t-SNE algorithm",
    long_description="Calculation and visualization of molecular networks based on t-SNE algorithm",
    keywords=["chemistry", "molecular networking", "mass spectrometry"],
    license="GPLv3+",
    classifiers=["Development Status :: 5 - Production/Stable",
                 "Intended Audience :: Science/Research",
                 "Intended Audience :: Developers",
                 "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
                 "Operating System :: OS Independent",
                 "Topic :: Scientific/Engineering :: Bio-Informatics",
                 "Topic :: Scientific/Engineering :: Chemistry",
                 "Programming Language :: Python :: 3",
                 "Programming Language :: Python :: 3.6",
                 "Programming Language :: Python :: 3.7",
                 "Programming Language :: Python :: 3.8",
                 "Programming Language :: Python :: 3.9"],
    packages=find_packages(exclude=("metgem_packaging", "tests",)),
    scripts=['MetGem', 'metgem-cli'],
    data_files=data_files,
    package_dir={'metgem': 'metgem'},
    package_data=package_data,
    include_package_data=True,
    cmdclass=versioneer.get_cmdclass({'process_resource': ProcessResourceCommand,
                                      'process_ui': ProcessUICommand,
                                      'build_py': BuildPyCommand}),
    zip_safe=False
)
