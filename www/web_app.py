import logging

logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from aiohttp import web
from factories import logger_factory, data_factory, response_factory
from coreweb import add_routes, add_static


def init_jinja2(app, **kwargs):
    logging.info('init jinja2...')
    options = dict(
        autoescape=kwargs.get('autoescape', True),
        block_start_string=kwargs.get('block_start_string', '{%'),
        block_end_string=kwargs.get('block_end_string', '%}'),
        variable_start_string=kwargs.get('variable_start_string', '{{'),
        variable_end_string=kwargs.get('variable_end_string', '}}'),
        auto_reload=kwargs.get('auto_reload', True)
    )
    path = kwargs.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('jinja template path is set to: %s' % path)
    env = Environment(loader=FileSystemLoader(path), **options)
    filter = kwargs.get('filter', None)
    if filter is not None:
        for name, f in filter.items():
            env.filters[name] = f
    app['__templating__'] = env


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1 minute ago'
    if delta < 3600:
        return u'%s minutes ago' % (delta // 60)
    if delta < 86400:
        return u'%s hours ago' % (delta // 3600)
    if delta < 604800:
        return u'%s days ago' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s/%s/%s' % (dt.month, dt.day, dt.year)


async def init(loop):
    app = web.Application(loop=loop, middlewares=[logger_factory, data_factory, response_factory])
    init_jinja2(app, filter=dict(datetime=datetime_filter))
    add_routes(app, 'handler')
    add_static(app)
    # app.router.add_route('GET', '/', index)
    srv = await loop.create_server(app.make_handler(), '0.0.0.0', 8080)
    logging.info('server started at http://127.0.0.1:8080...')
    return srv


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
