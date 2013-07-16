# Copyright (C) 2012 Linaro Limited
#
# Author: Andy Doan <andy.doan@linaro.org>
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
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import codecs
import contextlib
import cStringIO
import logging
import os
import stat
import subprocess

import lava_dispatcher.device.boot_options as boot_options

from lava_dispatcher.device.target import (
    Target
)
from lava_dispatcher.client.lmc_utils import (
    image_partition_mounted,
    generate_android_image,
    generate_fastmodel_image,
)
from lava_dispatcher.downloader import (
    download_image,
)
from lava_dispatcher.test_data import (
    create_attachment,
)
from lava_dispatcher.utils import (
    ensure_directory,
    extract_targz,
    DrainConsoleOutput,
)


class FastModelTarget(Target):

    PORT_PATTERN = 'terminal_0: Listening for serial connection on port (\d+)'
    ANDROID_WALLPAPER = 'system/wallpaper_info.xml'
    SYS_PARTITION = 2
    DATA_PARTITION = 5

    def __init__(self, context, config):
        super(FastModelTarget, self).__init__(context, config)

        self._sim_proc = None

        self._axf = None
        self._kernel = None
        self._dtb = None
        self._initrd = None
        self._uefi = None
        self._bootloader = 'u_boot'

    def _customize_android(self):
        with image_partition_mounted(self._sd_image, self.DATA_PARTITION) as d:
            wallpaper = '%s/%s' % (d, self.ANDROID_WALLPAPER)
            # delete the android active wallpaper as slows things down
            self.context.run_command('sudo rm -f %s' % wallpaper)

        with image_partition_mounted(self._sd_image, self.SYS_PARTITION) as d:
            with open('%s/etc/mkshrc' % d, 'a') as f:
                f.write('\n# LAVA CUSTOMIZATIONS\n')
                #make sure PS1 is what we expect it to be
                f.write('PS1="%s"\n' % self.ANDROID_TESTER_PS1)
                if not self.config.enable_network_after_boot_android:
                    # fast model usermode networking does not support ping
                    f.write('alias ping="echo LAVA-ping override 1 received"\n')

        self.deployment_data = Target.android_deployment_data

    def _copy_needed_files_from_partition(self, partno, subdir):
        with image_partition_mounted(self._sd_image, partno) as mntdir:
            subdir = os.path.join(mntdir, subdir)
            self._copy_needed_files_from_directory(subdir)

    def _copy_first_find_from_list(self, subdir, odir, file_list):
        f_path = None
        for fname in file_list:
            f_path = self._find_and_copy(subdir, odir, fname)
            if f_path:
                break

        return f_path

    def _copy_needed_files_from_directory(self, subdir):
        odir = os.path.dirname(self._sd_image)
        if self._bootloader == 'u_boot':
            # Extract the bootwrapper from the image
            if self.config.simulator_axf_files and self._axf is None:
                self._axf = self._copy_first_find_from_list(subdir, odir,
                                                            self.config.simulator_axf_files)
            # Extract the kernel from the image
            if self.config.simulator_kernel_files and self._kernel is None:
                self._kernel = self._copy_first_find_from_list(subdir, odir,
                                                               self.config.simulator_kernel_files)
            # Extract the initrd from the image
            if self.config.simulator_initrd_files and self._initrd is None:
                self._initrd = self._copy_first_find_from_list(subdir, odir,
                                                               self.config.simulator_initrd_files)
            # Extract the dtb from the image
            if self.config.simulator_dtb and self._dtb is None:
                self._dtb = self._find_and_copy(
                    subdir, odir, self.config.simulator_dtb)
        elif self._bootloader == 'uefi':
            # Extract the uefi binary from the image
            if self.config.simulator_uefi and self._uefi is None:
                self._uefi = self._find_and_copy(
                    subdir, odir, self.config.simulator_uefi)

    def _check_needed_files(self):
        if self._bootloader == 'u_boot':
            # AXF is needed when we are not using UEFI
            if self._axf is None and self.config.simulator_axf_files:
                raise RuntimeError('No AXF found, %r' %
                                   self.config.simulator_axf_files)
            # Kernel is needed only for b.L models
            if self._kernel is None and self.config.simulator_kernel_files:
                raise RuntimeError('No KERNEL found, %r' %
                                   self.config.simulator_kernel_files)
            # Initrd is needed only for b.L models
            if self._initrd is None and self.config.simulator_initrd_files:
                raise RuntimeError('No INITRD found, %r' %
                                   self.config.simulator_initrd_files)
            # DTB is needed only for b.L models
            if self._dtb is None and self.config.simulator_dtb:
                raise RuntimeError('No DTB found, %r' %
                                   self.config.simulator_dtb)
        elif self._bootloader == 'uefi':
            # UEFI binary is needed when specified
            if self._uefi is None and self.config.simulator_uefi:
                raise RuntimeError('No UEFI binary found, %r' %
                                   self.config.simulator_uefi)

    def deploy_android(self, boot, system, data):
        logging.info("Deploying Android on %s" % self.config.hostname)

        self._boot = download_image(boot, self.context, decompress=False)
        self._data = download_image(data, self.context, decompress=False)
        self._system = download_image(system, self.context, decompress=False)

        self._sd_image = '%s/android.img' % os.path.dirname(self._system)

        generate_android_image(
            self.context, 'vexpress-a9', self._boot, self._data, self._system, self._sd_image
        )

        self._copy_needed_files_from_partition(self.config.boot_part, '')

        self._customize_android()

    def deploy_linaro(self, hwpack=None, rootfs=None, bootloader='u_boot'):
        hwpack = download_image(hwpack, self.context, decompress=False)
        rootfs = download_image(rootfs, self.context, decompress=False)
        odir = os.path.dirname(rootfs)

        self._bootloader = bootloader

        generate_fastmodel_image(self.context, hwpack, rootfs, odir, bootloader)
        self._sd_image = '%s/sd.img' % odir

        self._copy_needed_files_from_directory(odir)
        self._copy_needed_files_from_partition(self.config.boot_part, 'rtsm')
        self._copy_needed_files_from_partition(self.config.root_part, 'boot')

        self._customize_linux(self._sd_image)

    def deploy_linaro_prebuilt(self, image):
        self._sd_image = download_image(image, self.context)

        self._copy_needed_files_from_partition(self.config.boot_part, 'rtsm')
        self._copy_needed_files_from_partition(self.config.root_part, 'boot')

        self._customize_linux(self._sd_image)

    @contextlib.contextmanager
    def file_system(self, partition, directory):
        with image_partition_mounted(self._sd_image, partition) as mntdir:
            path = '%s/%s' % (mntdir, directory)
            ensure_directory(path)
            yield path

    def extract_tarball(self, tarball_url, partition, directory='/'):
        logging.info('extracting %s to target' % tarball_url)

        with image_partition_mounted(self._sd_image, partition) as mntdir:
            tb = download_image(tarball_url, self.context, decompress=False)
            extract_targz(tb, '%s/%s' % (mntdir, directory))

    def _fix_perms(self):
        """ The directory created for the image download/creation gets created
        with tempfile.mkdtemp which grants permission only to the creator of
        the directory. We need group access because the dispatcher may run
        the simulator as a different user
        """
        d = os.path.dirname(self._sd_image)
        os.chmod(d, stat.S_IRWXG | stat.S_IRWXU)
        os.chmod(self._sd_image, stat.S_IRWXG | stat.S_IRWXU)
        if self._axf:
            os.chmod(self._axf, stat.S_IRWXG | stat.S_IRWXU)
        if self._kernel:
            os.chmod(self._kernel, stat.S_IRWXG | stat.S_IRWXU)
        if self._initrd:
            os.chmod(self._initrd, stat.S_IRWXG | stat.S_IRWXU)
        if self._dtb:
            os.chmod(self._dtb, stat.S_IRWXG | stat.S_IRWXU)
        if self._uefi:
            os.chmod(self._uefi, stat.S_IRWXG | stat.S_IRWXU)

        #lmc ignores the parent directories group owner
        st = os.stat(d)
        os.chown(self._sd_image, st.st_uid, st.st_gid)
        if self._axf:
            os.chown(self._axf, st.st_uid, st.st_gid)
        if self._kernel:
            os.chown(self._kernel, st.st_uid, st.st_gid)
        if self._initrd:
            os.chown(self._initrd, st.st_uid, st.st_gid)
        if self._dtb:
            os.chown(self._dtb, st.st_uid, st.st_gid)
        if self._uefi:
            os.chown(self._uefi, st.st_uid, st.st_gid)

    def _enter_bootloader(self):
        if self.proc.expect(self.config.interrupt_boot_prompt) != 0:
            raise Exception("Failed to enter bootloader")
        self.proc.sendline(self.config.interrupt_boot_command)

    def power_off(self, proc):
        super(FastModelTarget, self).power_off(proc)
        if self._sim_proc is not None:
            self._sim_proc.close()
            self._sim_proc = None

    def _create_rtsm_ostream(self, ofile):
        """the RTSM binary uses the windows code page(cp1252), but the
        dashboard and celery needs data with a utf-8 encoding"""
        return codecs.EncodedFile(ofile, 'cp1252', 'utf-8')

    def _drain_sim_proc(self):
        """pexpect will continue to get data for the simproc process. We need
        to keep this pipe drained so that it won't get full and then stop block
        the process from continuing to execute"""

        f = cStringIO.StringIO()
        self._sim_proc.logfile = self._create_rtsm_ostream(f)
        DrainConsoleOutput(proc=self._sim_proc).start()

    def power_on(self):
        if self._sim_proc is not None:
            logging.warning("device was still on, shutting down")
            self.power_off(None)

        self._check_needed_files()

        self._fix_perms()

        options = boot_options.as_string(self, join_pattern=' -C %s=%s')

        if self.config.simulator_boot_wrapper and self._uefi is None:
            options = '%s %s' % (self.config.simulator_boot_wrapper, options)

        sim_cmd = '%s %s' % (self.config.simulator_command, options)
        sim_cmd = sim_cmd.format(
            AXF=self._axf, IMG=self._sd_image, KERNEL=self._kernel,
            DTB=self._dtb, INITRD=self._initrd, UEFI=self._uefi)

        # the simulator proc only has stdout/stderr about the simulator
        # we hook up into a telnet port which emulates a serial console
        logging.info('launching fastmodel with command %r' % sim_cmd)
        self._sim_proc = self.context.spawn(sim_cmd, timeout=1200)
        self._sim_proc.expect(self.PORT_PATTERN, timeout=300)
        self._serial_port = self._sim_proc.match.groups()[0]
        logging.info('serial console port on: %s' % self._serial_port)

        match = self._sim_proc.expect(["ERROR: License check failed!",
                                       "Simulation is started"])
        if match == 0:
            raise RuntimeError("fast model license check failed")

        self._drain_sim_proc()

        logging.info('simulator is started connecting to serial port')
        self.proc = self.context.spawn(
            'telnet localhost %s' % self._serial_port,
            timeout=1200)
        self.proc.logfile_read = self._create_rtsm_ostream(
            self.proc.logfile_read)

        if self._uefi:
            self._enter_bootloader()
            self._customize_bootloader()

        return self.proc

    def get_test_data_attachments(self):
        """returns attachments to go in the "lava_results" test run"""
        # if the simulator never got started we won't even get to a logfile
        if getattr(self._sim_proc, 'logfile', None) is not None:
            if getattr(self._sim_proc.logfile, 'getvalue', None) is not None:
                content = self._sim_proc.logfile.getvalue()
                return [create_attachment('rtsm.log', content)]
        return []

    def get_device_version(self):
        cmd = self.config.simulator_version_command
        try:
            return subprocess.check_output(cmd, shell=True).strip()
        except subprocess.CalledProcessError:
            return "unknown"


target_class = FastModelTarget
