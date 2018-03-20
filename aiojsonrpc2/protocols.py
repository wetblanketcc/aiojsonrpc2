import asyncio
import json
import logging
import ssl

from .connection import Connection
from .errors import *

logger = logging.getLogger(__name__)


class BaseProtocol(object):
    log_prefix = ''
    connection_settings = {}

    stopping = False

    async def handle_connection(self, reader, writer):
        raise NotImplementedError

    async def loop(self, connection):
        raise NotImplementedError

    def set_connection_config(self, settings):
        self.connection_settings = settings

    def build_connection(self, reader, writer):
        return Connection(reader, writer)

    def cleanup_connection(self, connection):
        pass

    async def process(self, connection):
        is_notification = False
        response = {'id': None}
        try:
            data = await connection.read()

            # JSON-RPC: if `id` is not in the request data or is `None`, we
            # must consider it to be a notification
            _id = data.get('id')
            response['id'] = _id
            is_notification = _id is None

            jsonrpc_version = data.get('jsonrpc', '').strip()
            if jsonrpc_version:
                # JSON-RPC: for version 2 of the spec, this must be '2.0'
                if jsonrpc_version != '2.0':
                    logger.debug('{} invalid version `{}`'.format(self.log_prefix, jsonrpc_version))
                    raise JSONRPCInvalidRequest
                response['jsonrpc'] = jsonrpc_version

            # JSON-RPC: `method` is required!
            method = data.get('method')
            if method is None:
                logger.debug('{} `method` parameter missing from request `{}`'.format(self.log_prefix, json.dumps(data)))
                raise JSONRPCMethodNotFound

            # JSON-RPC: params are not required
            params = data.get('params')
            if params is not None and not isinstance(params, (list, dict)):
                raise JSONRPCInvalidParams

            # valid methods will be identically named to the incoming
            # method, with `.` replaced by `_` and prefaced with `handle_`
            handler_name = 'handle_' + method.replace('.', '_')

            try:
                logger.debug('{} handling {} {}, {}'.format(
                    self.log_prefix, method,
                    'notification' if is_notification else 'request',
                    params))

                # all handlers must be asyncio coroutines
                result = await getattr(self, handler_name)(connection, params, is_notification=is_notification)
                if not is_notification:
                    response['result'] = result
                    logger.debug('{} handling {} response, {}'.format(
                        self.log_prefix, method, result))
            except AttributeError:
                raise JSONRPCMethodNotFound('handler `{}` not found'.format(handler_name))
            except (asyncio.TimeoutError, asyncio.CancelledError, JSONRPCBaseError):
                # make sure these are not swallowed up by the
                # following `Exception` clause
                raise
            except Exception as e:
                raise JSONRPCInternalError('{} handler `{}` unknown error: {}'.format(
                    self.log_prefix, handler_name, str(e)))

        except JSONRPCError as e:
            logger.debug('{} {} {} ({})'.format(
                self.log_prefix, e.code, str(e), connection.peername))

            if not is_notification:
                response['error'] = {'code': e.code, 'message': e.msg}
                if 'id' not in response:
                    # JSONRPC spec says that on error, `id` must be `NULL`
                    # (Python's `None`) if it isn't already set
                    response['id'] = None

        if not is_notification:
            await connection.send(response, wait=False)

    async def close(self):
        pass


class ServerProtocol(BaseProtocol):
    clients = {}
    servers = []
    connection_settings = []

    def __init__(self, settings, *args, **kwargs):
        if isinstance(self.connection_settings, dict):
            self.set_connection_config([settings])
        else:
            self.set_connection_config(settings)

    async def start_listening(self):
        for settings in self.connection_settings:
            opts = {
                'host': settings.get('host') or '',  # default to all network interfaces
                'port': settings.get('port'),
            }

            use_ssl = settings.get('ssl', False)
            ssl_cert_file = settings.get('ssl_cert_file', '')
            ssl_cert_key_file = settings.get('ssl_cert_key_file', '')
            if use_ssl:
                if ssl_cert_file and ssl_cert_key_file:
                    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                    ssl_ctx.load_cert_chain(ssl_cert_file, ssl_cert_key_file)
                    ssl_ctx.options |= ssl.OP_NO_SSLv2
                    ssl_ctx.options |= ssl.OP_NO_SSLv3
                    opts['ssl'] = ssl_ctx
                else:
                    logger.warning('{} unable to secure connection, missing parameters'.format(
                        self.log_prefix))
                    use_ssl = False

            s = await asyncio.start_server(self.handle_connection, **opts)
            self.servers.append(s)

            bound_to = ", ".join(sorted(
                ["|".join([str(t) for t in t.getsockname()[:2]]) for t in s.sockets]))

            logger.info('{} accepting {} connections on {}'.format(
                self.log_prefix, 'secure' if use_ssl else 'plaintext', bound_to))

    async def handle_connection(self, reader, writer):
        conn = self.build_connection(reader, writer)
        fut = asyncio.ensure_future(self.loop(conn))
        self.clients[conn] = fut

    async def loop(self, connection):
        logger.info('{} peer connected {}'.format(self.log_prefix, connection.peername))

        while not self.stopping:
            try:
                await self.process(connection)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await self.close_connection(connection)
                break
            except JSONRPCNetworkDisconnection:
                await self.close_connection(connection)
                break

        logger.info('{} peer disconnected {}'.format(self.log_prefix, connection.peername))

    async def broadcast(self, method, params, is_notification=False):
        logger.debug('{} broadcasting {}, {}'.format(self.log_prefix, method, params))
        for connection in self.clients.keys():
            await connection.rpc(method, params, is_notification)

    async def close_connection(self, connection):
        self.clients.pop(connection, None)
        await connection.close()
        self.cleanup_connection(connection)

    async def close_all_connections(self):
        for connection, fut in self.clients.items():
            await connection.close()
            self.cleanup_connection(connection)

        await asyncio.gather(*self.clients.values())

        self.clients.clear()

    async def close(self):
        self.stopping = True

        await self.close_all_connections()

        for s in self.servers:
            s.close()
            await s.wait_closed()

        self.servers.clear()


class ClientProtocol(BaseProtocol):
    connection = None
    loop_future = None

    def __init__(self, settings, *args, **kwargs):
        self.set_connection_config(settings)

    @property
    def connected(self):
        return bool(self.connection)

    async def connect(self):
        if not self.connected:
            opts = {
                'host': self.connection_settings.get('host'),
                'port': self.connection_settings.get('port'),
            }
            use_ssl = self.connection_settings.get('ssl', False)
            if use_ssl:
                ssl_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                ssl_ctx.options |= ssl.OP_NO_SSLv2
                ssl_ctx.options |= ssl.OP_NO_SSLv3

                if not self.connection_settings.get('ssl_verify', False):
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = ssl.CERT_NONE

                opts['ssl'] = ssl_ctx

            try:
                fut = asyncio.open_connection(**opts)
                reader, writer = await asyncio.wait_for(fut, timeout=3)
            except Exception as e:
                logger.warning("{} unable to connect to {} ({})".format(
                    self.log_prefix, "|".join([str(opts['host']), str(opts['port'])]), str(e)))
                raise JSONRPCNetworkError

            logger.info('{} {}connection established to {}'.format(
                self.log_prefix, "secure " if use_ssl else "",
                "|".join([str(opts['host']), str(opts['port'])])))

            await self.handle_connection(reader, writer)

    async def handle_connection(self, reader, writer):
        self.connection = self.build_connection(reader, writer)
        self.loop_future = asyncio.ensure_future(self.loop(self.connection))

    async def loop(self, connection):
        while not self.stopping:
            try:
                await self.process(self.connection)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await self.close_connection()
                break
            except JSONRPCNetworkDisconnection:
                logger.info('{} peer disconnected {}'.format(self.log_prefix, connection.peername))
                await self.close_connection()
                break

    async def close_connection(self):
        if self.connection:
            await self.connection.close()
            self.cleanup_connection(self.connection)
            self.connection = None

    async def close(self):
        self.stopping = True
        await self.close_connection()

        if self.loop_future:
            await self.loop_future
