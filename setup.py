#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name="lava-dispatcher",
    version=":versiontools:lava_dispatcher:",
    url='https://launchpad.net/lava-dispatcher',
    license='GPL v2 or later',
    description="Part of the LAVA framework for dispatching test jobs",
    author='Linaro Validation Team',
    author_email='linaro-dev@lists.linaro.org',
    namespace_packages=['lava'],
    entry_points="""
    [lava.commands]
    dispatch = lava.dispatcher.commands:dispatch
    """,
    packages=find_packages(),
    package_data= {
        'lava_dispatcher': [
            'default-config/lava-dispatcher/lava-dispatcher.conf',
            'default-config/lava-dispatcher/lava-dispatcher.conf',
            'default-config/lava-dispatcher/device-defaults.conf',
            'default-config/lava-dispatcher/device-types/*.conf',
            'default-config/lava-dispatcher/devices/*.conf',
            ],
        },
    install_requires=[
        "pexpect >= 2.3",
        "lava-tool",
        "json-schema-validator",
    ],
    setup_requires=[
        'versiontools >= 1.8',
    ],
    scripts = [
        'lava-dispatch'
    ],
)
