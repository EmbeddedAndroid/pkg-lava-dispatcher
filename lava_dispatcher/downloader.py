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

import atexit
import bz2
import contextlib
import logging
import os
import re
import shutil
import subprocess
import time
import traceback
import urllib2
import urlparse
import zlib

from tempfile import mkdtemp


@contextlib.contextmanager
def _scp_stream(url, proxy=None, cookies=None):
    process = None
    try:
        process = subprocess.Popen(
            ['ssh', url.netloc, 'cat', url.path],
            shell=False,
            stdout=subprocess.PIPE
        )
        yield process.stdout
    finally:
        if process:
            process.kill()


@contextlib.contextmanager
def _http_stream(url, proxy=None, cookies=None):
    resp = None
    handlers = []
    if proxy:
        handlers = [urllib2.ProxyHandler({'http': '%s' % proxy})]
    opener = urllib2.build_opener(*handlers)

    if cookies:
        opener.addheaders.append(('Cookie', cookies))

    try:
        url = urllib2.quote(url.geturl(), safe=":/")
        resp = opener.open(url, timeout=30)
        yield resp
    finally:
        if resp:
            resp.close()


@contextlib.contextmanager
def _file_stream(url, proxy=None, cookies=None):
    fd = None
    try:
        fd = open(url.path, 'rb')
        yield fd
    finally:
        if fd:
            fd.close()


@contextlib.contextmanager
def _decompressor_stream(url, imgdir, decompress):
    fd = None
    decompressor = None

    fname,suffix = _url_to_fname_suffix(url, imgdir)

    if suffix == 'gz' and decompress:
        decompressor = zlib.decompressobj(16+zlib.MAX_WBITS)
    elif suffix == 'bz2' and decompress:
        decompressor = bz2.BZ2Decompressor()
    else:
        fname = '%s.%s' % (fname, suffix) #don't remove the file's real suffix

    def write(buff):
        if decompressor:
            buff = decompressor.decompress(buff)
        fd.write(buff)

    try:
        fd = open(fname, 'wb')
        yield (write,fname)
    finally:
        if fd:
            fd.close


def _url_to_fname_suffix(url, path='/tmp'):
    filename = os.path.basename(url.path)
    parts = filename.split('.')
    suffix = parts[-1]
    filename = os.path.join(path, '.'.join(parts[:-1]))
    return (filename, suffix)


def _url_mapping(url, context):
    '''allows the downloader to override a URL so that something like:
     http://blah/ becomes file://localhost/blah
    '''
    mappings = '%s/urlmappings.txt' % context.config.config_dir
    if os.path.exists(mappings):
        newurl = url
        with open(mappings, 'r') as f:
            for line in f.readlines():
                pat,rep = line.split(',')
                pat = pat.strip()
                rep = rep.strip()
                newurl = re.sub(pat, rep, newurl)
        if newurl != url:
            url = newurl
            logging.info('url mapped to: %s', url)
    return url


def download_image(url, context, imgdir=None,
                    delete_on_exit=True, decompress=True):
    '''downloads a image that's been compressed as .bz2 or .gz and
    optionally decompresses it on the file to the cache directory
    '''
    logging.info("Downloading image: %s" % url)
    if not imgdir:
        imgdir = mkdtemp(dir=context.config.lava_image_tmpdir)
        if delete_on_exit:
            atexit.register(shutil.rmtree, imgdir)

    url = _url_mapping(url, context)

    url = urlparse.urlparse(url)
    if url.scheme == 'scp':
        reader = _scp_stream
    elif url.scheme == 'http' or url.scheme == 'https':
        reader = _http_stream
    elif url.scheme == 'file':
        reader = _file_stream
    else:
        raise Exception("Unsupported url protocol scheme: %s" % url.scheme)

    cookies = context.config.lava_cookies
    with reader(url, context.config.lava_proxy, cookies) as r:
        with _decompressor_stream(url, imgdir, decompress) as (writer, fname):
            bsize = 32768
            buff = r.read(bsize)
            while buff:
                writer(buff)
                buff = r.read(bsize)
    return fname


def download_with_retry(context, imgdir, url, decompress=True, timeout=300):
    '''
    download test result with a retry mechanism and 5 minute default timeout
    '''
    logging.info("About to download %s to the host" % url)
    now = time.time()
    tries = 0

    while True:
        try:
            return download_image(url, context, imgdir, decompress)
        except:
            logging.warn("unable to download: %r" % traceback.format_exc())
            tries += 1
            if time.time() >= now + timeout:
                raise RuntimeError(
                    'downloading %s failed after %d tries' % (url, tries))
            else:
                logging.info('Sleep one minute and retry (%d)' % tries)
                time.sleep(60)
