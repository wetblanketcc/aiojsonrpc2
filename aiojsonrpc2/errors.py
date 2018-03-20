class JSONRPCBaseError(Exception):
    pass


class JSONRPCNetworkError(JSONRPCBaseError):
    pass


class JSONRPCNetworkDisconnection(JSONRPCNetworkError):
    pass


class JSONRPCError(JSONRPCBaseError):
    def __init__(self, code, msg=''):
        self.code = code
        self.msg = msg


class JSONRPCParseError(JSONRPCError):
    def __init__(self, msg=''):
        super().__init__(-32700, msg or "Parse error")


class JSONRPCInvalidRequest(JSONRPCError):
    def __init__(self, msg=''):
        super().__init__(-32600, msg or "Invalid Request")


class JSONRPCMethodNotFound(JSONRPCError):
    def __init__(self, msg=''):
        super().__init__(-32601, msg or "Method not found")


class JSONRPCInvalidParams(JSONRPCError):
    def __init__(self, msg=''):
        super().__init__(-32602, msg or "Invalid params")


class JSONRPCInternalError(JSONRPCError):
    def __init__(self, msg=''):
        super().__init__(-32603, msg or "Internal error")
