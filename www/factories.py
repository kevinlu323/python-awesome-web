import asyncio, logging, json

logging.basicConfig(level=logging.INFO)
from aiohttp import web
from urllib import parse


async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Incoming HTTP Request: %s, %s' % (request.method, request.path))
        return await handler(request)

    return logger


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


async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        res = await handler(request)
        if isinstance(res, web.StreamResponse):
            return res
        if isinstance(res, bytes):
            final_res = web.Response(body=res)
            final_res.content_type = 'application/octet-stream'
            return final_res
        if isinstance(res, str):
            if res.startswith('redirect:'):
                return web.HTTPFound(res[9:])
            final_res = web.Response(body=res.encode('utf-8'))
            final_res.content_type = 'text/html;charset=utf-8'
            return final_res
        if isinstance(res, dict):
            template = res.get('__template__')
            if template is None:
                final_res = web.Response(
                    body=json.dumps(res, ensure_ascii=False, default=lambda x: x.__dict__).encode('utf-8'))
                final_res.content_type = 'application/json;charset=utf-8'
                return final_res
            else:
                res['__user__'] = request.__user__
                final_res = web.Response(
                    body=app['__templating__'].get_template(template).render(**res).encode('utf-8'))
                final_res.content_type = 'text/html;charset=utf-8'
                return final_res
        if isinstance(res, int) and 100 <= res <= 600:
            return web.Response(status=res)
        if isinstance(res, tuple) and len(res) == 2:
            status, message = res
            if isinstance(status, int) and 100 <= status <= 600:
                return web.Response(status=status, text=str(message))
        final_res = web.Response(body=str(res).encode('utf-8'))
        final_res.content_type = 'text/plain;charset=utf-8'
        return final_res

    return response
