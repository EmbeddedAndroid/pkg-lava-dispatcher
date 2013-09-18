# Copyright (C) 2011 Linaro Limited
#
# Author: Paul Larson <paul.larson@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses>.

from lava_dispatcher.actions import BaseAction


class cmd_deploy_linaro_image(BaseAction):

    # This is how the schema for parameters should look, but there are bugs in
    # json_schema_validation that means it doesn't work (see
    # https://github.com/zyga/json-schema-validator/pull/6).

    ## parameters_schema = {
    ##     'type': [
    ##         {
    ##             'type': 'object',
    ##             'properties': {
    ##                 'image': {'type': 'string'},
    ##                 },
    ##             'additionalProperties': False,
    ##             },
    ##         {
    ##             'type': 'object',
    ##             'properties': {
    ##                 'hwpack': {'type': 'string'},
    ##                 'rootfs': {'type': 'string'},
    ##                 'rootfstype': {'type': 'string', 'optional': True, 'default': 'ext3'},
    ##                 },
    ##             'additionalProperties': False,
    ##             },
    ##         ],
    ##     }

    parameters_schema = {
        'type': 'object',
        'properties': {
            'hwpack': {'type': 'string', 'optional': True},
            'rootfs': {'type': 'string', 'optional': True},
            'image': {'type': 'string', 'optional': True},
            'rootfstype': {'type': 'string', 'optional': True},
            'bootloadertype': {'type': 'string', 'optional': True, 'default': 'u_boot'},
            'role': {'type': 'string', 'optional': True},
        },
        'additionalProperties': False,
    }

    @classmethod
    def validate_parameters(cls, parameters):
        super(cmd_deploy_linaro_image, cls).validate_parameters(parameters)
        if 'hwpack' in parameters:
            if 'rootfs' not in parameters:
                raise ValueError('must specify rootfs when specifying hwpack')
            if 'image' in parameters:
                raise ValueError('cannot specify image and hwpack')
        elif 'image' not in parameters:
            raise ValueError('must specify image if not specifying a hwpack')

    def run(self, hwpack=None, rootfs=None, image=None, rootfstype='ext3', bootloadertype='u_boot'):
        self.client.deploy_linaro(
            hwpack=hwpack, rootfs=rootfs, image=image, rootfstype=rootfstype, bootloadertype=bootloadertype)


class cmd_deploy_linaro_android_image(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'boot': {'type': 'string'},
            'system': {'type': 'string'},
            'data': {'type': 'string'},
            'rootfstype': {'type': 'string', 'optional': True, 'default': 'ext4'},
        },
        'additionalProperties': False,
    }

    def run(self, boot, system, data, rootfstype='ext4'):
        self.client.deploy_linaro_android(boot, system, data, rootfstype)


class cmd_deploy_linaro_kernel(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'kernel': {'type': 'string', 'optional': False},
            'ramdisk': {'type': 'string', 'optional': True},
            'dtb': {'type': 'string', 'optional': True},
            'rootfs': {'type': 'string', 'optional': True},
            'bootloader': {'type': 'string', 'optional': True},
            'firmware': {'type': 'string', 'optional': True},
            'rootfstype': {'type': 'string', 'optional': True},
            'bootloadertype': {'type': 'string', 'optional': True, 'default': 'u_boot'},
            'role': {'type': 'string', 'optional': True},
        },
        'additionalProperties': False,
    }

    @classmethod
    def validate_parameters(cls, parameters):
        super(cmd_deploy_linaro_kernel, cls).validate_parameters(parameters)
        if 'kernel' not in parameters:
            raise ValueError('must specify a kernel')

    def run(self, kernel=None, ramdisk=None, dtb=None, rootfs=None, bootloader=None,
            firmware=None, rootfstype='ext4', bootloadertype='u_boot'):
        self.client.deploy_linaro_kernel(
            kernel=kernel, ramdisk=ramdisk, dtb=dtb, rootfs=rootfs,
            bootloader=bootloader, firmware=firmware, rootfstype=rootfstype,
            bootloadertype=bootloadertype)


class cmd_dummy_deploy(BaseAction):

    parameters_schema = {
        'type': 'object',
        'properties': {
            'target_type': {'type': 'string', 'enum': ['ubuntu', 'oe', 'android', 'fedora']},
        },
        'additionalProperties': False,
    }

    def run(self, target_type):
        device = self.client.target_device
        device.deployment_data = device.target_map[target_type]
