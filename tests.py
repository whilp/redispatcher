import logging
import unittest

import redispatcher

from redispatcher import fmtcmd, wirecmd

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
