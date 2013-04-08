from commands import getoutput, getstatusoutput
import contextlib
import logging
import pexpect
import re
import os
from tempfile import mkdtemp
import sys

from lava_dispatcher.downloader import (
    download_image,
    )
from lava_dispatcher.utils import (
    logging_system,
    )


def generate_image(client, hwpack_url, rootfs_url, outdir, bootloader='u_boot', rootfstype=None,
                   extra_boot_args=None, image_size=None):
    """Generate image from a hwpack and rootfs url

    :param hwpack_url: url of the Linaro hwpack to download
    :param rootfs_url: url of the Linaro image to download
    """
    logging.info("preparing to deploy on %s" % client.config.hostname)
    logging.info("  hwpack: %s" % hwpack_url)
    logging.info("  rootfs: %s" % rootfs_url)

    logging.info("Downloading the %s file" % hwpack_url)
    hwpack_path = download_image(hwpack_url, client.context, outdir, decompress=False)

    logging.info("Downloading the %s file" % rootfs_url)
    rootfs_path = download_image(rootfs_url, client.context, outdir, decompress=False)

    logging.info("linaro-media-create version information")
    cmd = "linaro-media-create -v"
    rc, output = getstatusoutput(cmd)
    metadata = client.context.test_data.get_metadata()
    metadata['target.linaro-media-create-version'] = output
    client.context.test_data.add_metadata(metadata)

    image_file = os.path.join(outdir, "lava.img")

    logging.info("client.device_type = %s" %client.config.device_type)

    cmd = ("flock /var/lock/lava-lmc.lck linaro-media-create --hwpack-force-yes --dev %s "
           "--image-file %s --binary %s --hwpack %s --image-size 3G --bootloader %s" %
           (client.config.lmc_dev_arg, image_file, rootfs_path, hwpack_path, bootloader))
    if rootfstype is not None:
        cmd += ' --rootfs ' + rootfstype
    if image_size is not None:
        cmd += ' --image-size ' + image_size
    if extra_boot_args is not None:
        cmd += ' --extra-boot-args "%s"' % extra_boot_args
    logging.info("Executing the linaro-media-create command")
    logging.info(cmd)

    _run_linaro_media_create(client.context, cmd)
    return image_file

def generate_fastmodel_image(context, hwpack, rootfs, odir, bootloader='u_boot', size="2000M"):
    cmd = ("flock /var/lock/lava-lmc.lck sudo linaro-media-create "
           "--dev fastmodel --output-directory %s --image-size %s "
           "--hwpack %s --binary %s --hwpack-force-yes --bootloader %s" %
            (odir, size, hwpack, rootfs, bootloader) )
    logging.info("Generating fastmodel image with: %s" % cmd)
    _run_linaro_media_create(context, cmd)

def generate_android_image(context, device, boot, data, system, ofile, size="2000M"):
    cmd = ("flock /var/lock/lava-lmc.lck linaro-android-media-create "
           "--dev %s --image_file %s --image_size %s "
           "--boot %s --userdata %s --system %s" %
            (device, ofile, size, boot, data, system) )
    logging.info("Generating android image with: %s" % cmd)
    _run_linaro_media_create(context, cmd)

def get_partition_offset(image, partno):
    cmd = 'parted %s -m -s unit b print' % image
    part_data = getoutput(cmd)
    pattern = re.compile('%d:([0-9]+)B:' % partno)
    for line in part_data.splitlines():
        found = re.match(pattern, line)
        if found:
            return found.group(1)
    return None


@contextlib.contextmanager
def image_partition_mounted(image_file, partno):
    mntdir = mkdtemp()
    image = image_file
    offset = get_partition_offset(image, partno)
    mount_cmd = "mount -o loop,offset=%s %s %s" % (offset, image, mntdir)
    rc = logging_system(mount_cmd)
    if rc != 0:
        os.rmdir(mntdir)
        raise RuntimeError("Unable to mount image %s at offset %s" % (
            image, offset))
    try:
        yield mntdir
    finally:
        logging_system('umount ' + mntdir)
        logging_system('rm -rf ' + mntdir)

def _run_linaro_media_create(context, cmd):
    """Run linaro-media-create and accept licenses thrown up in the process.
    """
    proc = context.spawn(cmd)

    # This code is a bit out of control.  It describes a state machine.  Each
    # state has a name, a mapping patterns to wait for -> state to move to, a
    # timeout for how long to wait for said pattern and optionally some input
    # to send to l-m-c when you enter the step.

    # The basic outline is this:

    # We wait for l-m-c to actually start.  This has an enormous timeout,
    # because 'cmd' starts with 'flock /var/lock/lava-lmc.lck' and when lots
    # of jobs start at the same time, it can be a long time before the lock is
    # acquired.

    # Once its going, we watch for a couple of key phrases that suggets a
    # license popup has appeared.  The next few states navigate through the
    # dialogs and then accept the license.  The 'say-yes' state has extra fun
    # stuff to try to move to a state where the "<Ok>" button is highlighted
    # before pressing space (the acceptance dialogs are not consistent about
    # whether <Ok> is the default or not!).

    states = {
        'waiting': {
            'expectations': {
                "linaro-hwpack-install": 'default',
                },
            'timeout': 86400,
            },
        'default': {
            'expectations': {
                "TI TSPA Software License Agreement": 'accept-tspa',
                "SNOWBALL CLICK-WRAP": 'accept-snowball',
                "LIMITED LICENSE AGREEMENT FOR APPLICATION  DEVELOPERS": 'accept-snowball',
                },
            'timeout': 3600,
            },
        'accept-tspa': {
            'expectations': {"<Ok>": 'accept-tspa-1'},
            'timeout': 1,
            },
        'accept-tspa-1': {
            'input': "\t ",
            'expectations': {
                "Accept TI TSPA Software License Agreement": 'say-yes',
                },
            'timeout': 1,
            },
        'say-yes': {
            'expectations': {
                "  <(Yes|Ok)>": 'say-yes-tab',
                "\\033\[41m<(Yes|Ok)>": 'say-yes-space',
                },
            'timeout': 1,
            },
        'say-yes-tab': {
            'input': "\t",
            'expectations': {
                ".": 'say-yes',
                },
            'timeout': 1,
            },
        'say-yes-space': {
            'input': " ",
            'expectations': {
                ".": 'default',
                },
            'timeout': 1,
            },
        'accept-snowball': {
            'expectations': {"<Ok>": 'accept-snowball-1'},
            'timeout': 1,
            },
        'accept-snowball-1': {
            'input': "\t ",
            'expectations': {
                "Do you accept": 'say-yes',
                },
            'timeout': 1,
            },
        }


    state = 'waiting'

    while True:
        state_data = states[state]
        patterns = []
        next_state_names = []
        if 'input' in state_data:
            proc.send(state_data['input'])
        for pattern, next_state in state_data['expectations'].items():
            patterns.append(pattern)
            next_state_names.append(next_state)
        patterns.append(pexpect.EOF)
        next_state_names.append(None)
        logging.debug('waiting for %r' % patterns)
        match_id = proc.expect(patterns, timeout=state_data['timeout'])
        state = next_state_names[match_id]
        if state is None:
            return

