import asyncio
from collections import namedtuple
import json
import logging
from contextlib import suppress

from .errors import *

logger = logging.getLogger(__name__)

MAX_REQUEST_ID = 2**31


JSONRPCResponse = namedtuple('RPCResponse', ['success', 'data'])


class Connection(object):
    reader = writer = None
    peername = ''
    next_future_id = 0
    result_futures = {}

    def __init__(self, reader, writer, **kwargs):
        self.reader = reader
        self.writer = writer
        self.extra = kwargs
        # TODO: if haproxy PROXY logic is added, `peername` won't have the correct origin IP
        self.peername = reader._transport.get_extra_info('peername')

    def _handle_result(self, response):
        if isinstance(response, dict):
            success = True
            data = response.get('result')
            if data is None:
                success = False
                data = response.get('error')

            _id = response.get('id')
            if _id is not None and data is not None:
                _fut = self.result_futures.pop(_id, None)
                if not _fut:
                    # NOTE: there should always be a future for a response; a response
                    # here indicates it was NOT a notification request in the first place
                    logger.debug('no result future found for {}'.format(_id))
                else:
                    _fut.set_result(JSONRPCResponse(success, data))
                return True

        return False

    async def read(self):
        while True:
            data = (await self.reader.readline()).decode("utf-8")
            if not data:
                await self.close()
                raise JSONRPCNetworkDisconnection

            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                # TODO: there might be some haproxy PROXY protocol support needed in here
                logger.debug('JSONRPC connection: invalid JSON data `{}`'.format(data.rstrip('\n')))
                raise JSONRPCParseError

            if isinstance(data, list):
                is_result = False

                for _data in data:
                    res = self._handle_result(_data)
                    is_result = is_result or res

                if is_result:
                    # if we get in here, it was a handled response, so don't
                    # allow it to be processed as a request in the ensuing logic
                    continue
            elif isinstance(data, dict):
                if self._handle_result(data):
                    # if we get in here, it was a handled response, so don't
                    # allow it to be processed as a request in the ensuing logic
                    continue
            else:
                # if not a list or dict, it must have been parsed as a number
                # or string, which JSONRPC doesn't support
                logger.debug('JSONRPC connection: invalid JSONRPC data `{}`'.format(data.rstrip('\n')))
                raise JSONRPCParseError

            return data

    async def send(self, data, wait=True):
        self.writer.write((json.dumps(data) + "\n").encode())
        if wait:
            await self.writer.drain()

    def _build_rpc(self, method, params=None, is_notification=False):
        data = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or []
        }

        future = None
        if not is_notification:
            self.next_future_id += 1
            if self.next_future_id >= MAX_REQUEST_ID:
                self.next_future_id = 1
            data['id'] = self.next_future_id

            future = asyncio.Future()
            self.result_futures[self.next_future_id] = future

        return data, future

    async def rpc_batch(self, batch_data):
        requests = futures = []
        wait_needed = False

        # data must come in a list of 3-tuples (method, params, is_notification)
        for method, params, is_notification in batch_data:
            wait_needed = wait_needed or not is_notification
            data, future = self._build_rpc(method, params, is_notification)
            requests.append(data)
            futures.append(future)

        await self.send(requests, wait=False)

        # don't wait for a response if they're all notifications
        if wait_needed:
            # TODO: need to handle error responses here?
            # TODO: if there was a parse error, it will wait forever... do we need a timeout?
            return await asyncio.gather(*futures)

    async def rpc(self, method, params=None, is_notification=False, **kwargs):
        data, future = self._build_rpc(method, params, is_notification)

        await self.send(data, wait=False)

        # don't wait for a response if it's a notification
        if not is_notification:
            timeout = kwargs.get('timeout')
            if timeout:
                return await asyncio.wait_for(future, timeout)
            return await future

    async def close(self):
        if self.writer:
            self.writer.close()

        for fut in self.result_futures.values():
            fut.cancel()
            with suppress(asyncio.CancelledError):
                await fut

        self.result_futures.clear()
