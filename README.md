**`aiojsonrpc2` is a Python3 JSONRPC module built using `asyncio`.**

* Supports Python 3.5+ only (uses `async`/`await` syntax)
* Plain socket transport (not JSONRPC over HTTP)
* Supports secure TLS (ie. SSL) sockets

This is a new, fast, and modern JSONRPC module originally built to support [`aiostratum_proxy`](https://github.com/wetblanketcc/aiostratum_proxy) (a next-gen, extensible cryptocurrency mining proxy). However, releasing it as it's own independent Python package made the most sense.

#### Installation

There are currently no external dependencies required for `aiojsonrpc2`, and installation is simple:

```
pip install aiojsonrpc2
```

#### Usage

To use `aiojsonrpc2` and depending on your needs, you need to implement either a client or server 'protocol'. Both `ClientProtocol` and `ServerProtocol` let you handle bi-directional JSONRPC communication.

All incoming JSONRPC requests infer a protocol instance method from the JSONRPC `method` parameter. For example, if the `method` contains `client.show_message`, then the protocol class implementation must have an instance method called `handle_client_show_message`:

```
from aiojsonrpc2 import ClientProtocol, ServerProtocol

class MyClientProtocol(ClientProtocol):
    # NOTE: the opposing connection (perhaps a server) would
    # have sent the `client.show_message` request;
    # bidirectional communication!
    def handle_client_show_message(self, connection, params, **kwargs):
        # assuming the message to show is `params[0]`
        print(params[0])
```

Note how all `.` (ie. full stops/periods) from the JSONRPC `method` parameter are replaced by `_` (ie. underscore).

#### Future Considerations

Community involvement is appreciated. [Code review](https://github.com/wetblanketcc/aiojsonrpc2), [pull requests for bug fixes & improvements](https://github.com/wetblanketcc/aiojsonrpc2/pulls), [reporting issues](https://github.com/wetblanketcc/aiojsonrpc2/issues), spreading the word - all appreciated.

##### TODO:

* tests
* travis integration
* handle [haproxy `PROXY` protocol](http://www.haproxy.org/download/1.8/doc/proxy-protocol.txt)
