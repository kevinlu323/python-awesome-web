import asyncio, logging

logging.basicConfig(level=logging.INFO)
from aiohttp import web
from urllib import parse


async def data_factory(app, handler):
    async def parse_data(request):
        logging.info('data_factory')
        if request.method in ('PUT', 'POST'):
            if not request.content_type:
                return web.HTTPBadRequest(text='missing content-type!')
            content_type = request.content_type.lower()
            if content_type.startswith('application/json'):
                request.__data__ = await request.json()
                if not isinstance(request.__data__, dict):
                    return web.HTTPBadRequest(text='invalid json data, json body must be object.')
                logging.info('request json: %s' % request.__data__)
            elif content_type.startswith('application/x-www-form-urlencoded', 'multipart/form-data'):
                params = await request.post()
                request.__data__ = dict(**params)
                logging.info('request form: %s' % request.__data__)
            else:
                return web.HTTPBadRequest(text='Unsupported content-type: %s' % content_type)
        elif request.method == 'GET':
            qs = request.query_string
            request.__data__ = {k: v[0] for k, v in parse.parse_qs(qs, True).items()}
            logging.info('request query: %s' % request.__data__)
        else:
            request.__data__ = dict()
        return await handler(request)

    return parse_data
