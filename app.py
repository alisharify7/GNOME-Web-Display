#!/usr/bin/env python3
"""Authenticated dashboard and WHEP gateway; use start.sh for the desktop host."""
import argparse
import asyncio
import contextlib
from dataclasses import dataclass, field
import html
import json
import re
import signal
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit

try:
    from aiohttp import ClientError, ClientSession, ClientTimeout, web
except ImportError:
    raise SystemExit('ERROR: aiohttp is missing. Run bash setup.sh, or install python3-aiohttp for this Python interpreter.')

from input_protocol import InputState
from security import LoginLimiter, Sessions, constant_equal
from settings import ROOT, VERSION, ConfigError, load_settings, read_password

COOKIE = 'gwd_session'


@dataclass
class Runtime:
    cfg: object
    password: str
    demo: bool = False
    host: object = None
    sessions: Sessions = None
    limiter: LoginLimiter = field(default_factory=LoginLimiter)
    sockets: dict = field(default_factory=dict)
    client: object = None
    audio_lock: object = None
    started: float = field(default_factory=time.monotonic)

    def __post_init__(self):
        self.sessions = Sessions(ttl=self.cfg.session_hours * 3600)


STATE = web.AppKey('runtime', Runtime)


def authenticated(request):
    return request.app[STATE].sessions.valid(request.cookies.get(COOKIE, ''))


def expected_origin(request):
    cfg = request.app[STATE].cfg
    return cfg.public_origin or f'{request.scheme}://{request.host}'


@web.middleware
async def security_middleware(request, handler):
    try:
        # Strict same-origin writes, including sign-in; missing Origin is rejected.
        if request.method not in ('GET', 'HEAD', 'OPTIONS') or request.path == '/ws':
            if request.headers.get('Origin') != expected_origin(request):
                raise web.HTTPForbidden(text='Origin rejected. Use the same dashboard URL; review server.public_origin for HTTPS proxies.')
        if request.path not in ('/login', '/favicon.ico') and not authenticated(request):
            if request.path == '/':
                raise web.HTTPFound('/login')
            raise web.HTTPUnauthorized(text='Authentication required')
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    if not response.prepared:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


async def login_handler(request):
    state = request.app[STATE]
    error, status = '', 200
    if request.method == 'POST':
        peer = request.remote or 'unknown'
        if not state.limiter.allow(peer):
            raise web.HTTPTooManyRequests(text='Too many sign-in attempts. Wait one minute.', headers={'Retry-After': '60'})
        data = await request.post()
        username, password = data.get('username', ''), data.get('password', '')
        valid = isinstance(username, str) and isinstance(password, str)
        user_ok = constant_equal(username, state.cfg.user) if valid else False
        pass_ok = constant_equal(password, state.password) if valid else False
        if user_ok and pass_ok:
            state.limiter.clear(peer)
            state.sessions.revoke(request.cookies.get(COOKIE, ''))
            response = web.HTTPFound('/')
            response.set_cookie(COOKIE, state.sessions.create(), httponly=True, samesite='Strict',
                                secure=request.secure or state.cfg.public_origin.startswith('https://'),
                                max_age=state.cfg.session_hours * 3600, path='/')
            return response
        await asyncio.sleep(.2)
        error, status = 'Incorrect username or password.', 401
    page = (ROOT / 'login.html').read_text(encoding='utf-8')
    page = page.replace('__USER__', html.escape(state.cfg.user, quote=True))
    page = page.replace('__ERROR__', f'<div class="error" role="alert">{html.escape(error)}</div>' if error else '')
    return web.Response(text=page, content_type='text/html', status=status)


async def logout_handler(request):
    state = request.app[STATE]
    token = request.cookies.get(COOKIE, '')
    state.sessions.revoke(token)
    for ws, ws_token in list(state.sockets.items()):
        if ws_token == token:
            await ws.close(code=1008, message=b'Signed out')
    response = web.json_response({'ok': True})
    response.del_cookie(COOKIE, path='/')
    return response


async def index_handler(request):
    state = request.app[STATE]
    cfg = state.cfg
    url = '/demo-screen' if state.demo else f'/stream/{cfg.stream_name}/?controls=false&muted=true&autoplay=true&playsinline=true&disablepictureinpicture=true'
    text = (ROOT / 'index.html').read_text(encoding='utf-8')
    for key, value in {'STREAM_URL': url, 'WIDTH': str(cfg.width), 'HEIGHT': str(cfg.height),
                       'USER': html.escape(cfg.user), 'DEMO': 'true' if state.demo else 'false',
                       'VERSION': VERSION}.items():
        text = text.replace('__' + key + '__', value)
    return web.Response(text=text, content_type='text/html')


async def health_handler(request):
    state = request.app[STATE]
    cfg, host = state.cfg, state.host
    running = bool(host and host.GST_PROC and host.GST_PROC.poll() is None)
    source = host.AUDIO_SOURCE if host else None
    return web.json_response({
        'ok': state.demo or running, 'demo': state.demo, 'version': VERSION,
        'pipewire_node': host.NODE_ID if host else None,
        'width': cfg.width, 'height': cfg.height, 'fps': cfg.fps,
        'bitrate_kbps': cfg.bitrate, 'stream': cfg.stream_name,
        'gstreamer_running': running, 'audio_enabled': bool(source),
        'audio_source': source or 'off', 'audio_bitrate_kbps': cfg.audio_bitrate // 1000,
        'uptime_seconds': int(time.monotonic() - state.started), 'auth_user': cfg.user,
        'cursor_mode': 'embedded',
    })


async def audio_sources_handler(request):
    state = request.app[STATE]
    sources = await asyncio.to_thread(state.host.list_audio_sources) if state.host else []
    return web.json_response({'ok': True, 'current': (state.host.AUDIO_SOURCE or 'off') if state.host else 'off',
                              'sources': sources, 'demo': state.demo})


async def audio_switch_handler(request):
    state = request.app[STATE]
    if state.demo:
        return web.json_response({'ok': False, 'error': 'UI preview only: no real audio is captured.'}, status=409)
    if request.content_type != 'application/json':
        raise web.HTTPUnsupportedMediaType(text='Use application/json')
    try:
        data = await request.json()
    except (ValueError, UnicodeError):
        raise web.HTTPBadRequest(text='Invalid JSON body') from None
    if not isinstance(data, dict) or not isinstance(data.get('source'), str):
        raise web.HTTPBadRequest(text='Expected a JSON object with a source string')
    async with state.audio_lock:
        sources = await asyncio.to_thread(state.host.list_audio_sources)
        wanted = data['source']
        if wanted != 'off' and wanted not in {s['id'] for s in sources}:
            return web.json_response({'ok': False, 'error': 'Audio source is no longer available. Refresh the source list.'}, status=400)
        new_source = None if wanted == 'off' else wanted
        if new_source == state.host.AUDIO_SOURCE:
            return web.json_response({'ok': True, 'source': wanted, 'changed': False})
        try:
            await asyncio.to_thread(state.host.restart_gstreamer, new_source)
        except Exception as exc:
            print(f'Audio switch failed: {exc}', file=sys.stderr)
            return web.json_response({'ok': False, 'error': 'Audio switch failed; restoration was attempted. Check the host GStreamer log.'}, status=503)
    return web.json_response({'ok': True, 'source': wanted, 'changed': True, 'reload_delay_ms': 1000})


async def websocket_handler(request):
    state = request.app[STATE]
    if len(state.sockets) >= 16:
        raise web.HTTPServiceUnavailable(text='Too many input connections')
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=8192, compress=False)
    await ws.prepare(request)
    state.sockets[ws] = request.cookies.get(COOKIE, '')
    inputs = InputState(state.host, state.cfg.width, state.cfg.height) if state.host else None
    count, window = 0, time.monotonic()
    try:
        async for msg in ws:
            if not state.sessions.valid(state.sockets.get(ws, '')):
                await ws.close(code=1008, message=b'Session expired'); break
            if msg.type != web.WSMsgType.TEXT:
                continue
            now = time.monotonic()
            if now - window >= 1:
                count, window = 0, now
            count += 1
            if count > 600:
                await ws.close(code=1008, message=b'Input rate exceeded'); break
            try:
                data = json.loads(msg.data)
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object')
                if data.get('type') == 'ping':
                    await ws.send_json({'type': 'pong', 'ts': data.get('ts')})
                elif inputs:
                    await asyncio.to_thread(inputs.handle, data)
                # Demo acknowledges no input and never imports desktop APIs.
            except (ValueError, TypeError, KeyError) as exc:
                await ws.send_json({'type': 'error', 'error': str(exc)})
    finally:
        state.sockets.pop(ws, None)
        if inputs:
            await asyncio.to_thread(inputs.release)
    return ws


def allowed_proxy_path(tail, stream):
    # No arbitrary reverse proxy, traversal, WHIP publishing, or other streams.
    prefix = re.escape(stream)
    return bool(re.fullmatch(prefix + r'/(?:reader\.js|whep(?:/[a-fA-F0-9-]{36})?)?', tail))


def rewrite_location(value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != 'http' or parsed.netloc not in ('127.0.0.1:8889', 'localhost:8889'):
            raise ValueError('Unexpected upstream redirect')
    if not parsed.path.startswith('/') or parsed.path.startswith('//'):
        raise ValueError('Unexpected relative upstream redirect')
    return '/stream' + parsed.path + ('?' + parsed.query if parsed.query else '')


async def stream_proxy(request):
    state = request.app[STATE]
    if state.demo:
        raise web.HTTPNotFound(text='No media in UI preview')
    tail = request.match_info['tail']
    if not allowed_proxy_path(tail, state.cfg.stream_name):
        raise web.HTTPNotFound(text='Unknown stream resource')
    if request.method not in ('GET', 'HEAD', 'POST', 'PATCH', 'DELETE', 'OPTIONS'):
        raise web.HTTPMethodNotAllowed(request.method, ['GET', 'HEAD', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])
    upstream = f'http://127.0.0.1:8889/{tail}'
    if request.query_string:
        upstream += '?' + request.rel_url.raw_query_string
    excluded = {'host', 'cookie', 'authorization', 'origin', 'content-length', 'connection',
                'transfer-encoding', 'upgrade', 'proxy-authorization', 'te', 'trailer'}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded}
    try:
        async with state.client.request(request.method, upstream, headers=headers,
                                        data=await request.read(), allow_redirects=False) as response:
            payload = await response.read()
            output = {k: v for k, v in response.headers.items()
                      if k.lower() in ('content-type', 'content-encoding', 'etag', 'accept-patch', 'link')}
            if 'Location' in response.headers:
                output['Location'] = rewrite_location(response.headers['Location'])
            return web.Response(status=response.status, body=payload, headers=output)
    except (ClientError, asyncio.TimeoutError, ValueError) as exc:
        print(f'MediaMTX proxy error: {exc}', file=sys.stderr)
        raise web.HTTPBadGateway(text='Media service is unavailable. Check MediaMTX and the host terminal; then press Reconnect.') from None


async def favicon_handler(request):
    return web.Response(status=204)


async def demo_screen(request):
    if not request.app[STATE].demo:
        raise web.HTTPNotFound()
    return web.Response(text=(ROOT / 'demo.html').read_text(encoding='utf-8'), content_type='text/html')


async def expire_sockets(state):
    while True:
        await asyncio.sleep(2)
        for ws, token in list(state.sockets.items()):
            if not state.sessions.valid(token):
                await ws.close(code=1008, message=b'Session expired')


async def resources(app):
    state = app[STATE]
    state.audio_lock = asyncio.Lock()
    expiry = None
    try:
        if not state.demo:
            import host
            state.host = host
            host.initialize(state.cfg)
            threading.Thread(target=host.glib_loop_thread, daemon=True).start()
            host.create_virtual_monitor()
            await asyncio.to_thread(host.start_gstreamer)
        state.client = ClientSession(timeout=ClientTimeout(total=20), auto_decompress=False, trust_env=False)
        expiry = asyncio.create_task(expire_sockets(state))
        yield
    finally:
        for ws in list(state.sockets):
            await ws.close(code=1001, message=b'Server stopping')
        if expiry:
            expiry.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await expiry
        if state.client:
            await state.client.close()
        if state.host:
            await asyncio.to_thread(state.host.shutdown)


def create_app(cfg, password, demo=False):
    cfg.validate()
    if not 8 <= len(password) <= 1024:
        raise ConfigError('A password of 8-1024 characters is required; run ./start.sh.')
    app = web.Application(middlewares=[security_middleware], client_max_size=64 * 1024)
    app[STATE] = Runtime(cfg, password, demo)
    app.cleanup_ctx.append(resources)
    app.router.add_get('/login', login_handler)
    app.router.add_post('/login', login_handler)
    app.router.add_post('/logout', logout_handler)
    app.router.add_get('/', index_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/api/audio-sources', audio_sources_handler)
    app.router.add_post('/api/audio-source', audio_switch_handler)
    app.router.add_get('/demo-screen', demo_screen)
    app.router.add_get('/favicon.ico', favicon_handler)
    app.router.add_route('*', '/stream/{tail:.*}', stream_proxy)
    return app


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    cfg = load_settings(args.config)
    password = read_password(cfg)
    if args.demo:
        cfg.http_host, cfg.public_origin, cfg.tls_cert, cfg.tls_key = '127.0.0.1', '', '', ''
    app = create_app(cfg, password, args.demo)
    runner = web.AppRunner(app, access_log=None)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await runner.setup()
        tls = None
        if cfg.tls_cert:
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.minimum_version = ssl.TLSVersion.TLSv1_2
            tls.load_cert_chain(cfg.tls_cert, cfg.tls_key)
        site = web.TCPSite(runner, cfg.http_host, cfg.http_port, ssl_context=tls)
        await site.start()
        print(f'Ready: {"https" if tls else "http"}://{cfg.http_host}:{cfg.http_port} | GNOME Web Display {VERSION}', flush=True)
        if args.demo:
            print('DEMO: local interface preview only; no virtual monitor, audio, or host input.', flush=True)
        await stop.wait()
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'ERROR: {exc}\nRun ./start.sh --doctor and check the host log. See README.md for repair steps.', file=sys.stderr)
        raise SystemExit(1)
