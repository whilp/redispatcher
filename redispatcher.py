import asyncore
import logging
import optparse
import shlex
import socket
import sys
import time

import hiredis

__all__ = ["Redis", "DebugRedis"]

try:
    NullHandler = logging.NullHandler
except AttributeError:
    class NullHandler(logging.Handler):
        def emit(self, record): pass

log = logging.getLogger(__name__)
log.addHandler(NullHandler())

def wirecmd(command, args, separator="\r\n"):
    arglen = 1 + len(args)
    parts = ["*%d" % arglen]
    for arg in (command,) + args:
        arg = str(arg)
        parts.extend(["$%d" % len(arg), arg])
    parts.append('')

    return separator.join(parts)

def fmtcmd(command, args, separator=' '):
    parts = ["%s"]
    parts.extend("%r" for arg in args)
    return ' '.join(parts)

def logcmd(name, command, args, log=None, level=logging.DEBUG):
    parts = ["%s"]
    parts.extend("%r" for arg in args)

    if name is not None:
        log = logging.getLogger(name)
    log.log(level, fmtcmd(command, args), command, *args)

class Redis(asyncore.dispatcher):
    terminator = "\r\n"

    def __init__(self, sock=None, map=None):
        asyncore.dispatcher.__init__(self, sock=sock, map=map)
        self.callbacks = []
        self.buffer = ''
        self.reader = hiredis.Reader()

    def connect(self, host="localhost", port=6379, db=0, callback=None, data=None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        asyncore.dispatcher.connect(self, (host, port))
        self.socket.setblocking(0)
        self.set_socket(self.socket, self._map)
        log.debug("connected to %s:%d/%d", host, port, db)
        self.callbacks = [("CONNECT", (), callback, data)]

    def do(self, callback, data, command, *args):
        self.log_send(command, args)
        self.buffer += wirecmd(command, args, separator=self.terminator)
        self.callbacks.insert(1, (command, args, callback, data))

    def log(self, message):
        pass

    def log_info(self, message, type=None):
        pass

    def log_send(self, command, args):
        pass

    def log_recv(self, reply):
        pass

    def handle_connect(self): pass

    def handle_close(self):
        self.close()

    def handle_write(self):
        sent = self.send(self.buffer)
        self.buffer = self.buffer[sent:]

    def handle_read(self):
        self.reader.feed(self.recv(8192))

        while True:
            try:
                reply = self.reader.gets()
            except hiredis.ProtocolError:
                self.close()
                raise
            if reply is False:
                return

            self.log_recv(reply)
            command, args, callback, data = self.callbacks.pop()
            if callback is not None:
                callback(command, args, data, reply)

class DebugRedis(Redis):

    def log(self, message):
        log.debug(message)

    def log_info(self, message, type=None):
        log.debug(message)

    def log_send(self, command, args):
        logcmd("%s.client.tx" % __name__, command, args)

    def log_recv(self, reply):
        logging.getLogger("%s.client.rx" % __name__).debug("%r", reply)


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

    def cb_log(command, args, data, reply):
        (start,) = data
        seconds = time.time() - start
        cmd = fmtcmd(command, args) % ((command,) + args)
        log.debug("Ran %s in %g seconds", cmd, seconds)
        log.debug("Received: %r", reply)

    for line in stdin:
        splitted = shlex.split(line)
        command = splitted[0]
        args = splitted[1:]
        db.do(cb_log, (time.time(),), command, *args)

    asyncore.loop()

def run():
    try:
        ret = main(sys.argv, sys.stdin, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        ret = None

    sys.exit(ret)

if __name__ == "__main__": # pragma: nocover
    run()
