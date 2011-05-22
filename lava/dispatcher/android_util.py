import os
from uuid import uuid1
from datetime import datetime
import json
import subprocess
from lava.dispatcher.config import LAVA_RESULT_DIR
import time

# TODO: Result saving could be replaced by linaro_dashboard_bundle probably.
def savebundlefile(testname, results, starttime):
    """
    Save results as .bundle file under /tmp/LAVA_RESULT_DIR/
    """
    TIMEFORMAT = '%Y-%m-%dT%H:%M:%SZ'
    testdata = {}
    test_runs = [{}]
    testdata['format'] = "Dashboard Bundle Format 1.2"
    test_runs[0]['test_id'] = testname
    test_runs[0]['analyzer_assigned_uuid'] = str(uuid1())
    test_runs[0]['time_check_performed'] = False
    test_runs[0]['analyzer_assigned_date'] = starttime 
    # TODO: hw_context sw_context for android
    testdata['test_runs'] = test_runs
    testdata['test_runs'][0].update(results)
    bundle = testdata
    subprocess.call(["mkdir", "-p", "/tmp/%s" % LAVA_RESULT_DIR])
    # The file name should be unique to be distinguishable from others
    filename = "/tmp/%s/" % LAVA_RESULT_DIR + testname + \
        str(time.mktime(datetime.utcnow().timetuple())) + ".bundle"
    with open(filename, "wt") as stream:
        json.dump(bundle, stream)
