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

protolog = logging.getLogger("%s.protocol" % __name__)
wirelog = logging.getLogger("%s.wire" % __name__)

class Error(Exception): pass
class HandlerError(Error): pass

class Redis(asyncore.dispatcher):
    terminator = "\r\n"
    replytypes = {
        '+': "singleline",
        '-': "error",
        ':': "integer",
        '$': "bulk",
        '*': "multibulk",
    }

    def __init__(self, sock=None, map=None):
        asyncore.dispatcher.__init__(self, sock=sock, map=map)
        self.outbuf = ''
        self.inbuf = ''
        self.replytype = None

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
        logging.getLogger("%s.protocol.send" % log.name).debug(
            ' '.join(msg), command, *args)

        request = self.terminator.join(request)
        logging.getLogger("%s.write.send" % log.name).debug(
            "%r", request)

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
        if self.replytype is None:
            # XXX: Handle unknown reply type.
            self.replytype = self.replytypes[chunk[0]]
            chunk = chunk[1:]

        if self.replytype is "singleline":
            idx = chunk.find(self.terminator)
            if idx >= 0:
                reply = self.inbuf + chunk[:idx]
                chunk = chunk[idx:]
                logging.getLogger("%s.protocol.receive" % log.name).debug(
                    reply)

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

    format = "%(message)s"
    handler = logging.StreamHandler(stderr)
    handler.setFormatter(logging.Formatter(format))
    log.addHandler(handler)
    log.setLevel(level)

    db = Redis()
    db.connect()
    db.do("SELECT", 0)

    asyncore.loop()

if __name__ == "__main__": # pragma: nocover
    try:
        ret = main(sys.argv, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        ret = None

    sys.exit(ret)
