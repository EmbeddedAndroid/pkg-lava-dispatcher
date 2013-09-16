# Copyright (C) 2013 Linaro Limited
#
# Author: Tyler Baker <Tyler.Baker@linaro.org>
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import logging
import contextlib
import time
import os
import pexpect

from lava_dispatcher.device.target import (
    Target
)
from lava_dispatcher.client.base import (
    NetworkCommandRunner,
)
from lava_dispatcher.errors import (
    CriticalError,
)
from lava_dispatcher.device.fastboot import (
    FastbootTarget
)
from lava_dispatcher.device.master import (
    MasterImageTarget
)
from lava_dispatcher.utils import (
    mk_targz,
    rmtree,
)
from lava_dispatcher.downloader import (
    download_with_retry,
)


class CapriTarget(FastbootTarget, MasterImageTarget):

    def __init__(self, context, config):
        super(CapriTarget, self).__init__(context, config)

    def _enter_fastboot(self):
        if self.fastboot.on():
            logging.debug("Device is on fastboot - no need to hard reset")
            return
        try:
            self._soft_reboot()
            self._enter_bootloader(self.proc)
        except:
            logging.exception("_enter_bootloader failed")
            self._hard_reboot()
            self._enter_bootloader(self.proc)
        self.proc.sendline("fastboot")

    def deploy_android(self, boot, system, userdata):

        boot = self._get_image(boot)
        system = self._get_image(system)
        userdata = self._get_image(userdata)

        self._enter_fastboot()
        self.fastboot.flash('boot', boot)
        self.fastboot.flash('system', system)
        self.fastboot.flash('userdata', userdata)

        self.deployment_data = Target.ubuntu_deployment_data
        self.deployment_data['boot_image'] = boot

    def power_on(self):
        if not self.deployment_data.get('boot_image', False):
            raise CriticalError('Deploy action must be run first')

        if not self._booted:
            self._enter_fastboot()
            self.fastboot('reboot')
            self._wait_for_prompt(self.proc,
                                  self.context.device_config.master_str,
                                  self.config.boot_linaro_timeout)

            self._booted = True
            self.proc.sendline('')
            self.proc.sendline('')
            self.proc.sendline('export PS1="%s"' % self.deployment_data['TESTER_PS1'])
            self._runner = self._get_runner(self.proc)

        return self.proc

    @contextlib.contextmanager
    def file_system(self, partition, directory):
        try:
            pat = self.deployment_data['TESTER_PS1_PATTERN']
            incrc = self.deployment_data['TESTER_PS1_INCLUDES_RC']
            runner = NetworkCommandRunner(self, pat, incrc)

            targetdir = '/%s' % directory
            runner.run('mkdir -p %s' % targetdir)
            parent_dir, target_name = os.path.split(targetdir)
            runner.run('/bin/tar -cmzf /tmp/fs.tgz -C %s %s'
                       % (parent_dir, target_name))
            runner.run('cd /tmp')  # need to be in same dir as fs.tgz

            ip = runner.get_target_ip()

            self.proc.sendline('python -m SimpleHTTPServer 0 2>/dev/null')
            match_id = self.proc.expect([
                'Serving HTTP on 0.0.0.0 port (\d+) \.\.',
                pexpect.EOF, pexpect.TIMEOUT])
            if match_id != 0:
                msg = "Unable to start HTTP server on Capri"
                logging.error(msg)
                raise CriticalError(msg)
            port = self.proc.match.groups()[match_id]

            url = "http://%s:%s/fs.tgz" % (ip, port)

            logging.info("Fetching url: %s" % url)
            tf = download_with_retry(self.context, self.scratch_dir,
                                     url, False)

            tfdir = os.path.join(self.scratch_dir, str(time.time()))

            try:
                os.mkdir(tfdir)
                self.context.run_command('/bin/tar -C %s -xzf %s'
                                         % (tfdir, tf))
                yield os.path.join(tfdir, target_name)
            finally:
                tf = os.path.join(self.scratch_dir, 'fs.tgz')
                mk_targz(tf, tfdir)
                rmtree(tfdir)

                self.proc.sendcontrol('c')  # kill SimpleHTTPServer

                # get the last 2 parts of tf, ie "scratchdir/tf.tgz"
                tf = '/'.join(tf.split('/')[-2:])
                runner.run('rm -rf %s' % targetdir)
                self._target_extract(runner, tf, parent_dir)
        finally:
            self.proc.sendcontrol('c')  # kill SimpleHTTPServer

target_class = CapriTarget
