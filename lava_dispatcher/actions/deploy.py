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
from lava_dispatcher.client.fastmodel import LavaFastModelClient
from lava_dispatcher.client.master import LavaMasterImageClient
from lava_dispatcher.client.qemu import LavaQEMUClient


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
    ##                 'kernel_matrix': {'type': 'string', 'optional': True},
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
            'kernel_matrix': {'type': 'string', 'optional': True},
            'rootfstype': {'type': 'string', 'optional': True},
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
        elif 'kernel_matrix' in parameters:
            raise ValueError('cannot specify kernel_matrix with an image')

    def run(self, hwpack=None, rootfs=None, image=None, kernel_matrix=None,
            rootfstype='ext3'):
        if not isinstance(self.client, LavaMasterImageClient) and \
            not isinstance(self.client, LavaQEMUClient) and \
            not isinstance(self.client, LavaFastModelClient):
                raise RuntimeError("Invalid LavaClient for this action")

        self.client.deploy_linaro(
            hwpack=hwpack, rootfs=rootfs, image=image,
            kernel_matrix=kernel_matrix, rootfstype=rootfstype)
