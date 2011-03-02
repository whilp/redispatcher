import logging
import logging.handlers
import unittest

import redispatcher

from redispatcher import fmtcmd, logcmd, wirecmd

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record): pass

log = logging.getLogger(__name__)
log.addHandler(NullHandler())

class Stub(object):
    
    def __init__(self, obj, attr):
        self.obj = obj
        self.attr = attr
        self.unpatched = None
    
    def __call__(self, *args, **kwargs):
        return self.__class__(self.obj, self.attr)

    def __getattr_(self, attr):
        return self.__class__()

    def patch(self):
        self.unpatched = getattr(self.obj, self.attr)
        setattr(self.obj, self.attr, self)

        return self

    def unpatch(self):
        setattr(self.obj, self.attr, self.unpatched)
        self.unpatched = None

class BaseTest(unittest.TestCase):
    pass

class TestUtils(BaseTest):

    def test_wirecmd_noargs(self):
        result = wirecmd("COMMAND", tuple())

        self.assertEquals(result, "*1\r\n$7\r\nCOMMAND\r\n")

    def test_wirecmd_args(self):
        result = wirecmd("COMMAND", ("arg1", "arg2"))

        self.assertEquals(result,
                "*3\r\n$7\r\nCOMMAND\r\n$4\r\narg1\r\n$4\r\narg2\r\n")
    
    def test_wirecmd_separator(self):
        result = wirecmd("COMMAND", ("arg1", "arg2"), separator="!")

        self.assertEquals(result,
                "*3!$7!COMMAND!$4!arg1!$4!arg2!")

    def test_fmtcmd_noargs(self):
        result = fmtcmd("COMMAND", tuple())

        self.assertEquals(result, "%s")

    def test_fmtcmd_args(self):
        result = fmtcmd("COMMAND", ("arg1", "arg2"))

        self.assertEquals(result, "%s %r %r")

    def test_fmtcmd_separator(self):
        result = fmtcmd("COMMAND", ("arg1", "arg2"), separator="!")

        self.assertEquals(result, "%s!%r!%r")

def tmplog(name="tmp", size=100):
    log = logging.getLogger(name)
    log.propagate = 0
    buffer = logging.handlers.BufferingHandler(size)
    log.addHandler(buffer)
    log.buffer = buffer.buffer

    return log

class TestLogging(BaseTest):

    def setUp(self):
        BaseTest.setUp(self)
        self.log = tmplog()

    def test_logcmd_explicit_logger(self):
        logcmd(None, "COMMAND", ("arg1", "arg2"), log=self.log)

        self.assertEqual(len(self.log.buffer), 1)
        record = self.log.buffer[0]
        self.assertEqual(record.msg, "%s %r %r")
        self.assertEqual(record.args, ("COMMAND", "arg1", "arg2"))

    def test_logcmd_get_logger(self):
        logcmd("tmp", "COMMAND", ("arg1", "arg2"))

        self.assertEqual(len(self.log.buffer), 1)
        record = self.log.buffer[0]
        self.assertEqual(record.msg, "%s %r %r")
        self.assertEqual(record.args, ("COMMAND", "arg1", "arg2"))
