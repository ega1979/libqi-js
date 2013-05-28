#! /usr/bin/python2

import tornado
import tornadio2
import qi
import sys
import json
import base64

URL = None
sid = 1

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytearray):
            return base64.b64encode(obj)
        return json.JSONEncoder.default(self, obj)

class QiMessagingHandler(tornadio2.conn.SocketConnection):

    def on_open(self, info):
        global sid
        self.info = info
        self.sid = sid
        sid = sid + 1
        print("[%d] New connection from %s" % (self.sid, self.info.ip))
        self.qim = qi.Session()
        self.qim.connect(URL)

    def on_message(self, message):
        pass

    def reply(self, idm, mtype, data):
        try:
            evt = dict(name = mtype, args = { "idm": idm, "result": data })
            message = u'5:::%s' % (json.dumps(evt, cls=SetEncoder))
            self.session.send_message(message)
        except AttributeError as exc:
            print idm, str(exc)

    def do_callback(self, service, signal):
        def cbk(*args):
            self.reply(-1, "event",
                       { "service": service, "signal": signal, "data": args })
        return cbk

    def do_reply(self, idm):
        def rep(fut):
            if fut.has_error():
                self.reply(idm, "error", fut.error())
            else:
                self.reply(idm, "reply", fut.value())
        return rep

    @tornadio2.event
    def call(self, idm, params):
        try:
            service = params["service"]
            method = params["method"]
            args = params["args"]
            if service == "ServiceDirectory" and method == "service":
                obj = self.qim.service(str(args[0]))
                self.reply(idm, "reply", (args[0], obj.metaObject()))
            elif method == "registerEvent":
                obj = self.qim.service(str(service))
                evt = getattr(obj, args[0])
                eid = evt.connect(self.do_callback(service, args[0]))
                self.reply(idm, "reply", eid)
            elif method == "unregisterEvent":
                obj = self.qim.service(str(service))
                evt = getattr(obj, args[0])
                self.reply(idm, "reply", evt.disconnect(args[1]))
            else:
                obj = self.qim.service(str(service))
                met = getattr(obj, method)
                if args is None:
                    fut = met(_async = True)
                else:
                    fut = met(*args, _async = True)
                fut.add_callback(self.do_reply(idm))
        except (AttributeError, RuntimeError) as exc:
            self.reply(idm, 'error', str(exc))

    def on_close(self):
        self.qim.close()
        self.qim = None
        print("[%d] Disconnected" % (self.sid))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        URL = "tcp://127.0.0.1:9559"
    else:
        URL = sys.argv[1]

    print("Will connect to " + URL)

    QI_APP = qi.Application()

    ROUTER = tornadio2.router.TornadioRouter(QiMessagingHandler)

    SOCK_APP = tornado.web.Application(
      ROUTER.urls,
      socket_io_port = 8002
    )

    tornadio2.server.SocketServer(SOCK_APP, auto_start=False)

    tornado.ioloop.IOLoop.instance().start()
