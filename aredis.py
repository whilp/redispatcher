import asyncore
import logging
import optparse
import socket
import sys

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record): pass

log = logging.getLogger(__name__)
log.addHandler(NullHandler())

getLogger = logging.getLogger
name = log.name

protolog = logging.getLogger("%s.protocol" % __name__)
wirelog = logging.getLogger("%s.wire" % __name__)

class Error(Exception): pass
class HandlerError(Error): pass
class ReplyError(Error): pass

Nil = object()
Done = True

class Redis(asyncore.dispatcher):
    terminator = "\r\n"
    replyhandlers = {}

    def __init__(self, sock=None, map=None):
        asyncore.dispatcher.__init__(self, sock=sock, map=map)
        self.outbuf = ''
        self.inbuf = ''
        self.replyhandler = None
        self.firstbyte = None
        self.replylen = None
        self.multireply = None
        self.multireplylen = None
        self.reply = None

    def connect(self, host="localhost", port=6379, db=0):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        asyncore.dispatcher.connect(self, (host, port))
        self.socket.setblocking(0)
        self.set_socket(self.socket, self._map)
        log.debug("connected to %s:%d/%d", host, port, db)

    def do(self, command, *args):
        arglen = 1 + len(args)

        request = ["*%d" % arglen]
        for arg in (command,) + args:
            arg = str(arg)
            request.extend(["$%d" % len(arg), arg])
        request.append('')

        msg = ["%s"]
        msg.extend("%r" for arg in args)

        getLogger("%s.protocol.send" % name).debug(
            ' '.join(msg), command, *args)

        request = self.terminator.join(request)
        getLogger("%s.wire.send" % name).debug("%r", request)

        self.outbuf += request

    def log(self, message):
        log.debug(message)

    def log_info(self, message, type=None):
        log.debug(message)

    def writable(self):
        return self.outbuf and True

    def handle_connect(self): pass

    def handle_close(self):
        self.close()

    def handle_error(self):
        t, v, tb = sys.exc_info()

        if isinstance(v, HandlerError):
            log.info(v.args[0])
        else:
            asyncore.dispatcher.handle_error(self)

    def handle_write(self):
        sent = self.send(self.outbuf)
        self.outbuf = self.outbuf[sent:]

    def handle_read(self):
        chunk = self.recv(8192)
        self.inbuf += chunk
        if self.inbuf:
            self.dispatch()

    def dispatch(self):
        if self.replyhandler is None:
            self.firstbyte = self.inbuf[0]
            try:
                self.replyhandler = self.replyhandlers[self.firstbyte]
            except KeyError:
                pass
            if self.replyhandler is None:
                raise HandlerError(
                        "unrecognized handler for reply type %r" % self.firstbyte)
            self.inbuf = self.inbuf[1:]

        result = self.replyhandler(self)
        if self.reply is not None:
            self.handle_reply()
            self.reply = None
        if result is Done:
            self.replyhandler = None
            if self.inbuf:
                self.dispatch()

    def handle_reply(self):
        pass

    def handle_singleline_reply(self):
        idx = self.inbuf.find(self.terminator)
        if idx < 0:
            return

        reply = self.inbuf[:idx]
        self.inbuf = self.inbuf[idx + len(self.terminator):]
        name = log.name
        getLogger("%s.wire.receive" % name).debug("%r",
                "%s%s%s" % (self.firstbyte, reply, self.terminator))
        getLogger("%s.protocol.receive" % name).debug("%r", reply.strip())

        self.reply = reply
        return Done
    
    def handle_error_reply(self):
        ret = self.handle_singleline_reply()
        if self.reply is not None:
            self.reply = ReplyError(self.reply[4:])
        return ret

    def handle_integer_reply(self):
        ret = self.handle_singleline_reply()
        if self.reply is not None:
            self.reply = int(self.reply)
        return ret

    def handle_bulk_reply(self):
        if self.replylen is None:
            idx = self.inbuf.find(self.terminator)
            if idx > 0:
                replylen = self.inbuf[:idx]
                self.inbuf = self.inbuf[idx + len(self.terminator):]
                self.replylen = int(replylen)

        name = log.name
        if self.replylen == -1:
            reply = Nil
            getLogger("%s.wire.receive" % name).debug("%r",
                    "%s%d%s" % (self.firstbyte, -1, self.terminator))
        elif self.replylen is None or (len(self.inbuf) - 2) < self.replylen:
            return
        else:
            reply = self.inbuf[:self.replylen]
            self.inbuf = self.inbuf[self.replylen + len(self.terminator):]
            getLogger("%s.wire.receive" % name).debug("%r",
                    self.terminator.join((
                        "%s%s" % (self.firstbyte, self.replylen),
                        reply, "")))

        getLogger("%s.protocol.receive" % name).debug("%s",
                reply is Nil and "nil" or repr(reply))

        self.replylen = None
        if self.multireply is not None:
            self.multireply.append(reply)
            self.multireplylen -= 1
            if self.multireplylen == 0:
                self.reply = self.multireply
                self.multireply = None
                self.multireplylen = None
            return Done
        else:
            self.reply = reply
            return Done

    def handle_multibulk_reply(self):
        if self.multireplylen is None:
            idx = self.inbuf.find(self.terminator)
            if idx > 0:
                multireplylen = self.inbuf[:idx]
                self.inbuf = self.inbuf[idx + len(self.terminator):]
                self.multireplylen = int(multireplylen)
                self.multireply = []

        if self.multireplylen == 0:
            reply = []
            getLogger("%s.wire.receive" % name).debug(
                "%s",
                "%s%s%r" % (self.firstbyte, self.multireplylen, self.terminator))
            getLogger("%s.protocol.receive" % name).debug(
                "%r", reply)
            self.reply = reply
            return Done

        self.replyhandler = self.handle_bulk_reply
        return Done

    replyhandlers = {
        '+': handle_singleline_reply,
        '-': handle_error_reply,
        ':': handle_integer_reply,
        '$': handle_bulk_reply,
        '*': handle_multibulk_reply,
    }

def parseargs(argv):
    """Parse command line arguments.

    Returns a tuple (*opts*, *args*), where *opts* is an
    :class:`optparse.Values` instance and *args* is the list of arguments left
    over after processing.

    :param argv: a list of command line arguments, usually :data:`sys.argv`.
    """
    prog = argv[0]
    usage = "[options] <address>"
    parser = optparse.OptionParser(prog=prog, usage=usage)
    parser.allow_interspersed_args = False

    defaults = {
        "quiet": 0,
        "silent": False,
        "verbose": 0,
    }

    # Global options.
    parser.add_option("-q", "--quiet", dest="quiet",
        default=defaults["quiet"], action="count",
        help="decrease the logging verbosity")
    parser.add_option("-s", "--silent", dest="silent",
        default=defaults["silent"], action="store_true",
        help="silence the logger")
    parser.add_option("-v", "--verbose", dest="verbose",
        default=defaults["verbose"], action="count",
        help="increase the logging verbosity")

    (opts, args) = parser.parse_args(args=argv[1:])
    return (opts, args)

def main(argv, stdin=None, stdout=None, stderr=None):
    """Main entry point.

    Returns a value that can be understood by :func:`sys.exit`.

    :param argv: a list of command line arguments, usually :data:`sys.argv`.
    :param out: stream to write messages; :data:`sys.stdout` if None.
    :param err: stream to write error messages; :data:`sys.stderr` if None.
    """
    if stdin is None: # pragma: nocover
        stdin = sys.stdin
    if stdout is None: # pragma: nocover
        stdout = sys.stdout
    if stderr is None: # pragma: nocover
        stderr = sys.stderr

    (opts, args) = parseargs(argv)
    level = logging.WARNING - ((opts.verbose - opts.quiet) * 10)
    if opts.silent:
        level = logging.CRITICAL + 1
    level = max(1, level)

    format = "%(name)s %(message)s"
    handler = logging.StreamHandler(stderr)
    handler.setFormatter(logging.Formatter(format))
    log.addHandler(handler)
    log.setLevel(level)

    db = Redis()
    db.connect()
    db.do("SELECT", 0)
    db.do("LPUSH", "lrange", "foo")
    db.do("LRANGE", "lrange", 0, 1)
    db.do("LLEN", "lrange")

    asyncore.loop()

if __name__ == "__main__": # pragma: nocover
    try:
        ret = main(sys.argv, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        ret = None

    sys.exit(ret)
