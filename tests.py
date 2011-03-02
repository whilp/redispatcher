import logging
import logging.handlers
import unittest

import redispatcher

from redispatcher import Redis, fmtcmd, logcmd, wirecmd

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record): pass

log = logging.getLogger(__name__)
log.addHandler(NullHandler())

class Stub(object):
    
    def __init__(self, obj=None, attr=None, returns=[], raises=[]):
        self.obj = obj
        self.attr = attr
        self.unpatched = None
        self.called = []
        self.returns = returns
        self.raises = raises

    def __call__(self, *args, **kwargs):
        self.called.append((args, kwargs))
        if self.raises:
            raise self.raises.pop(0)
        elif self.returns:
            return self.returns.pop(0)
            
        return self.__class__(self.obj, self.attr)

    def __getattr__(self, attr):
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

class TestRedis(BaseTest):
    
    def setUp(self):
        BaseTest.setUp(self)
        self.socket = Stub(redispatcher.socket, "socket").patch()
        self.patched = [
            Stub(redispatcher.asyncore.dispatcher, "__init__").patch(),
            Stub(redispatcher.asyncore.dispatcher, "connect").patch(),
            Stub(redispatcher.asyncore.dispatcher, "set_socket").patch(),
            self.socket,
        ]
        self.redis = Redis()
        self.log = tmplog()
        self.log.orig = redispatcher.log
        redispatcher.log = self.log

    def tearDown(self):
        BaseTest.tearDown(self)
        for stub in self.patched:
            stub.unpatch()
        redispatcher.log = self.log.orig

    def test_init(self):
        redis = Redis()
        
    def test_connect(self):
        redis = self.redis
        sock = Stub()

        redis.connect(sock=sock, data="data", callback="callback")

        self.assertEqual(redis.callbacks, [("CONNECT", (), "callback", "data")])

    def test_connect_build_sock(self):
        redis = self.redis

        redis.connect()

        self.assertEqual(len(self.socket.called), 1)

    def test_do(self):
        redis = self.redis

        redis.do("callback", "data", "command", "arg1", "arg2")

        self.assertEqual(redis.buffer, 
           "*3\r\n$7\r\ncommand\r\n$4\r\narg1\r\n$4\r\narg2\r\n")
        self.assertEqual(redis.callbacks, 
            [('command', ('arg1', 'arg2'), 'callback', 'data')])

    def test_log_silent(self):
        redis = self.redis

        redis.log("log")
        redis.log_info("log_info")
        redis.log_send("log_send", ())
        redis.log_recv("log_recv")

        self.assertEqual(self.log.buffer, [])

class TestRedisReader(BaseTest):
    
    def setUp(self):
        BaseTest.setUp(self)
        self.redis = Redis()
        Stub(self.redis, "recv").patch()
        Stub(self.redis, "reader").patch()
        self.redis.callbacks = self.callbacks = [("command", "args", "callback", "data")]

    def test_handle_read_incomplete(self):
        redis = self.redis
        Stub(redis.reader, "gets", returns=[False]).patch()

        result = redis.handle_read()

        self.assertEqual(result, None)
        self.assertEqual(redis.callbacks, self.callbacks)

    def test_handle_read_exception(self):
        redis = self.redis
        error = redispatcher.ProtocolError
        Stub(redis.reader, "gets", raises=[error()]).patch()
        Stub(redis, "close").patch()

        self.assertRaises(error, redis.handle_read)
        self.assertEqual(len(redis.close.called), 1)
        self.assertEqual(redis.callbacks, self.callbacks)

    def test_handle_read_callback(self):
        redis = self.redis
        Stub(redis.reader, "gets", returns=["reply", False]).patch()
        callback = Stub()
        redis.callbacks = [("command", "args", callback, "data")]

        result = redis.handle_read()

        self.assertEqual(redis.callbacks, [])
        self.assertEqual(callback.called,
            [(('command', 'args', 'data', 'reply'), {})])
