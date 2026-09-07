#!/usr/bin/env python3
"""Offline screenshots of the actual UI, using explicit demo data.
No network, GNOME session, browser navigation, media, or performance claims.
For an end-to-end local-server browser check use tools/screenshots.py instead.
"""
import argparse
import html
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/images')
    parser.add_argument('--browser', default=shutil.which('chromium') or shutil.which('google-chrome'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    ui=(ROOT/'index.html').read_text()
    for key,value in {'WIDTH':'1920','HEIGHT':'1080','USER':'display','VERSION':'8.0.0','DEMO':'true','STREAM_URL':'about:blank'}.items():
        ui=ui.replace('__'+key+'__',value)
    ui=ui.replace('src="about:blank"','srcdoc="'+html.escape((ROOT/'demo.html').read_text(),quote=True)+'"')
    mock='''
    window.fetch=async function(path){
      const health={ok:true,demo:true,width:1920,height:1080,fps:60,bitrate_kbps:6000,
        pipewire_node:null,uptime_seconds:0,gstreamer_running:false,audio_source:'off',cursor_mode:'embedded'};
      const data=path==='/health'?health:{ok:true,current:'off',sources:[],demo:true};
      return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
    };
    window.WebSocket=class extends EventTarget{
      static OPEN=1;
      constructor(){super();this.readyState=0;setTimeout(()=>{this.readyState=1;this.dispatchEvent(new Event('open'));},0);}
      send(text){const m=JSON.parse(text);if(m.type==='ping')setTimeout(()=>this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({type:'pong',ts:m.ts})})),0);}
      close(){this.readyState=3;this.dispatchEvent(new Event('close'));}
    };
    '''
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.browser,headless=True,args=['--no-sandbox'])
        def page_for(width,height,mobile=False):
            context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1,
                                        is_mobile=mobile,has_touch=mobile)
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.evaluate('() => {' + mock + '}')
            page.set_content(ui,wait_until='load')
            page.wait_for_timeout(350)
            return page
        login=browser.new_page(viewport={'width':1440,'height':960})
        login.set_content((ROOT/'login.html').read_text().replace('__USER__','display').replace('__ERROR__',''))
        login.screenshot(path=str(args.output/'login-desktop.png')); login.close()
        page=page_for(1440,960)
        assert page.locator('#statusText').inner_text()=='Demo'
        page.screenshot(path=str(args.output/'desktop-dashboard.png'))
        page.click('#focusFab');page.wait_for_timeout(1800)
        assert 'focus-mode' in page.locator('body').get_attribute('class')
        page.screenshot(path=str(args.output/'desktop-focus.png'))
        page.click('#focusFab');page.click('#fullscreenBtn');page.wait_for_timeout(150)
        assert page.evaluate("document.fullscreenElement?.id === 'stage'")
        assert page.locator('#focusFab').is_visible()
        page.click('#focusFab');page.click('#focusFab');page.click('#fullscreenBtn')
        page.click('#keyboardBtn')
        assert 'hidden' not in page.locator('#keyboardPanel').get_attribute('class')
        page.click('#closeKeyboard')
        # Exercise pointer capture while dragging the focus control.
        box=page.locator('#focusFab').bounding_box()
        page.mouse.move(box['x']+20,box['y']+20);page.mouse.down()
        page.mouse.move(box['x']-80,box['y']+100,steps=6);page.mouse.up()
        m=page_for(430,932,True)
        assert 'hidden' in m.locator('#dashboard').get_attribute('class')
        m.screenshot(path=str(args.output/'mobile-display.png'))
        m.click('#dashboardBtn');m.wait_for_timeout(300)
        m.screenshot(path=str(args.output/'mobile-dashboard.png'))
        m.click('#keyboardBtn');m.wait_for_timeout(300)
        assert 'hidden' in m.locator('#dashboard').get_attribute('class')
        m.screenshot(path=str(args.output/'mobile-keyboard.png'))
        m.locator('[data-key="Control"]').click()
        assert 'active' in m.locator('[data-key="Control"]').get_attribute('class')
        m.click('#controlBtn')
        assert 'active' not in m.locator('[data-key="Control"]').get_attribute('class')
        for width in (320,360,390,430,768):
            m.set_viewport_size({'width':width,'height':932});m.wait_for_timeout(100)
            assert m.evaluate('document.documentElement.scrollWidth<=innerWidth'), f'Overflow at {width}px'
            for button in ('audioBtn','keyboardBtn','dashboardBtn','fullscreenBtn','logoutBtn'):
                box=m.locator('#'+button).bounding_box()
                assert box and box['x']>=0 and box['x']+box['width']<=width+1,(width,button,box)
        browser.close()
    if errors:
        raise AssertionError('JavaScript errors: '+'; '.join(errors))
    print('PASS: actual UI rendered offline with explicit demo/mock data.')
    print('PASS: desktop + mobile layouts, Focus toggle/drag, fullscreen Focus, keyboard, release-on-pause, widths 320/360/390/430/768.')
    print('PASS: no uncaught JavaScript errors. Six UI previews written; no live GNOME/MediaMTX session was used.')


if __name__=='__main__': main()
