import asyncio, inspect, functools, logging, os
from aiohttp import web
from api_errors import APIError

logging.basicConfig(level=logging.INFO)


def request_method(path, *, method):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.__method__ = method
        wrapper.__route__ = path
        return wrapper

    return decorator


get = functools.partial(request_method, method='GET')
post = functools.partial(request_method, method='POST')


class RequestHandler(object):
    '''
    RequestHandler will accept a http request, compare the parameters required
    by the function with parameters in the request, the function may not be a coroutine,
    so RequestHandler wrap it as a coroutine, then call the function, the function
    return web.Response object, with meet aiohttp framework design
    '''

    def __init__(self, func):
        self._func = func

    async def __call__(self, request):
        required_args = inspect.signature(self._func).parameters
        logging.info('handler function required args: %s' % required_args)

        # get parameters from the request
        inbound_kw = {k: v for k, v in request.__data__.items() if k in required_args}

        # get match_info, i.e. @get('/blog/{id}'), add to inbound_kw
        inbound_kw.update(request.match_info)

        # If request is required by the handler, add it
        if 'request' in required_args:
            inbound_kw['request'] = request

        # check if any required argument is missing from the inbound request
        for k, arg in required_args.items():
            if k == 'request' and arg.kind in (arg.VAR_POSITIONAL, arg.VAR_KEYWORD):
                return web.HTTPBadRequest(text='request parameter cannot be the var argument!')
            if arg.kind not in (arg.VAR_POSITIONAL, arg.VAR_KEYWORD):
                if arg.default == arg.empty and arg.name not in inbound_kw:
                    return web.HTTPBadRequest(text='Missing argument: %s' % arg.name)

        logging.info('calling handler function with args: %s' % inbound_kw)
        try:
            return await self._func(**inbound_kw)
        except APIError as e:
            return dict(error=e.error, data=e.date, message=e.message)


def add_routes(app, module_name):
    try:
        mod = __import__(module_name, fromlist=['get_submodule'])
    except ImportError as e:
        raise e
    # Traverse all mods, get handler functions
    # Find functions with '__method__' and '__route__' attributes
    for attr in dir(mod):
        # if Starts with '_', pass
        if attr.startswith('_'):
            continue
        func = getattr(mod, attr)
        if callable(func) and hasattr(func, '__method__') and hasattr(func, '__route__'):
            args = ','.join(inspect.signature(func).parameters.keys())
            logging.info('add route %s %s => %s(%s)' % (func.__method__, func.__route__, func.__name__, args))
            app.router.add_route(func.__method__, func.__route__, RequestHandler(func))


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))
