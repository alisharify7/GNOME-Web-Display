import asyncio
import unittest
from aiohttp import CookieJar, WSMsgType
from aiohttp.test_utils import TestClient, TestServer
from app import STATE, allowed_proxy_path, create_app, rewrite_location
from settings import Settings


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app=create_app(Settings(), 'test-password', demo=True)
        self.client=TestClient(TestServer(self.app),cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.origin=str(self.client.make_url('/')).rstrip('/')
        self.headers={'Origin':self.origin}

    async def asyncTearDown(self): await self.client.close()

    async def login(self):
        r=await self.client.post('/login',data={'username':'display','password':'test-password'},headers=self.headers,allow_redirects=False)
        self.assertEqual(r.status,302)
        return r

    async def test_login_page(self):
        r=await self.client.get('/login'); self.assertEqual(r.status,200)
        self.assertIn('GNOME Web Display',await r.text())
        self.assertEqual(r.headers['Cache-Control'],'no-store')

    async def test_protected_endpoints(self):
        for path in ['/health','/api/audio-sources','/demo-screen','/stream/monitor/']:
            r=await self.client.get(path); self.assertEqual(r.status,401,path)

    async def test_index_redirects(self):
        r=await self.client.get('/',allow_redirects=False); self.assertEqual(r.status,302)

    async def test_origin_required(self):
        r=await self.client.post('/login',data={'username':'display','password':'test-password'})
        self.assertEqual(r.status,403)

    async def test_cross_origin_rejected(self):
        r=await self.client.post('/login',headers={'Origin':'https://evil.example'},data={})
        self.assertEqual(r.status,403)

    async def test_bad_login(self):
        r=await self.client.post('/login',data={'username':'display','password':'wrong'},headers=self.headers)
        self.assertEqual(r.status,401)

    async def test_unicode_login(self):
        self.app[STATE].password='\u0631\u0645\u0632-123456'
        r=await self.client.post('/login',data={'username':'display','password':'\u0631\u0645\u0632-123456'},headers=self.headers,allow_redirects=False)
        self.assertEqual(r.status,302)

    async def test_cookie_flags(self):
        r=await self.login(); cookie=r.cookies['gwd_session']
        self.assertTrue(cookie['httponly']); self.assertEqual(cookie['samesite'],'Strict')

    async def test_demo_health_not_fake_streaming(self):
        await self.login(); r=await self.client.get('/health'); data=await r.json()
        self.assertTrue(data['demo']); self.assertFalse(data['gstreamer_running'])
        self.assertIsNone(data['pipewire_node']); self.assertEqual(data['audio_source'],'off')

    async def test_rendered_index(self):
        await self.login(); text=await (await self.client.get('/')).text()
        self.assertNotIn('__WIDTH__',text); self.assertIn('DEMO=true',text)

    async def test_logout_revokes_cookie(self):
        await self.login(); tokens=list(self.app[STATE].sessions.tokens)
        r=await self.client.post('/logout',headers=self.headers); self.assertEqual(r.status,200)
        self.assertFalse(self.app[STATE].sessions.valid(tokens[0]))
        self.assertEqual((await self.client.get('/health')).status,401)

    async def test_get_logout_disabled(self):
        await self.login(); self.assertEqual((await self.client.get('/logout')).status,405)

    async def test_demo_audio_disabled(self):
        await self.login(); r=await self.client.post('/api/audio-source',json={'source':'off'},headers=self.headers)
        self.assertEqual(r.status,409)

    async def test_websocket_ping(self):
        await self.login(); ws=await self.client.ws_connect('/ws',headers=self.headers)
        await ws.send_json({'type':'ping','ts':123})
        self.assertEqual(await ws.receive_json(),{'type':'pong','ts':123})
        await ws.close()

    async def test_websocket_bad_json(self):
        await self.login(); ws=await self.client.ws_connect('/ws',headers=self.headers)
        await ws.send_str('[]'); self.assertEqual((await ws.receive_json())['type'],'error')
        await ws.close()

    async def test_logout_closes_socket(self):
        await self.login(); ws=await self.client.ws_connect('/ws',headers=self.headers)
        task=asyncio.create_task(self.client.post('/logout',headers=self.headers))
        msg=await ws.receive(timeout=3)
        self.assertEqual(msg.type,WSMsgType.CLOSE)
        await task

    async def test_server_expiry(self):
        await self.login(); state=self.app[STATE]
        state.sessions.tokens={k:0 for k in state.sessions.tokens}
        self.assertEqual((await self.client.get('/health')).status,401)

    async def test_rate_limit(self):
        self.app[STATE].limiter.maximum=1
        await self.client.post('/login',data={},headers=self.headers)
        r=await self.client.post('/login',data={},headers=self.headers)
        self.assertEqual(r.status,429)

    async def test_body_limit(self):
        r=await self.client.post('/login',data={'password':'a'*70000},headers=self.headers)
        self.assertEqual(r.status,413)


class ProxyTests(unittest.TestCase):
    def test_allowed_resources(self):
        for path in ['monitor/','monitor/reader.js','monitor/whep','monitor/whep/12345678-1234-1234-1234-123456789012']:
            self.assertTrue(allowed_proxy_path(path,'monitor'),path)

    def test_disallowed_resources(self):
        for path in ['../','monitor/../x','monitor/whip','monitor/publish','other/','monitor/%2e%2e','//evil']:
            self.assertFalse(allowed_proxy_path(path,'monitor'),path)

    def test_location_rewrite(self):
        self.assertEqual(rewrite_location('/monitor/whep/id?q=1'),'/stream/monitor/whep/id?q=1')
        self.assertEqual(rewrite_location('http://127.0.0.1:8889/monitor/'),'/stream/monitor/')

    def test_external_location_rejected(self):
        for value in ['https://evil.example/path','//evil.example/path','relative/path']:
            with self.assertRaises(ValueError): rewrite_location(value)
