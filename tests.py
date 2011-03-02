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

class TestLogging(BaseTest):

    def setUp(self):
        self.log = log = logging.getLogger("tmp")
        log.propagate = 0
        buffer = logging.handlers.BufferingHandler(100)
        log.addHandler(buffer)
        self.buffer = buffer.buffer

    def test_logcmd_explicit_logger(self):
        logcmd(None, "COMMAND", ("arg1", "arg2"), log=self.log)

        self.assertEqual(len(self.buffer), 1)
        record = self.buffer[0]
        self.assertEqual(record.msg, "%s %r %r")
        self.assertEqual(record.args, ("COMMAND", "arg1", "arg2"))

    def test_logcmd_get_logger(self):
        logcmd("tmp", "COMMAND", ("arg1", "arg2"))

        self.assertEqual(len(self.buffer), 1)
        record = self.buffer[0]
        self.assertEqual(record.msg, "%s %r %r")
        self.assertEqual(record.args, ("COMMAND", "arg1", "arg2"))
