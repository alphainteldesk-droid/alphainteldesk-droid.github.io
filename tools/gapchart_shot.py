# Throwaway test helper (branch gapchart-test only): screenshots of the Live Gap Chart in all three places.
import threading, http.server, socketserver, os
from playwright.sync_api import sync_playwright
root=os.getcwd(); os.makedirs('out',exist_ok=True)
class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(s,*a,**k): super().__init__(*a,directory=root,**k)
    def log_message(self,*a): pass
srv=socketserver.TCPServer(('127.0.0.1',0),Q); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,name in ((1440,'desktop'),(390,'phone')):
        sc=1 if w>500 else 2
        pg=b.new_page(viewport={'width':w,'height':900},device_scale_factor=sc)
        pg.on('pageerror',lambda e:print('PAGEERROR',name,e))
        pg.goto(f'http://127.0.0.1:{port}/gap-scanner.html'); pg.wait_for_timeout(2500)
        pg.add_style_tag(content='header,nav,.topbar{position:static !important}')
        pg.query_selector('#gapchart').screenshot(path=f'out/gs-top-{name}.png')
        rows=pg.query_selector_all('#board .gp')
        print(name,'rows',len(rows),'row charts',len(pg.query_selector_all('#board .gc-row')))
        for i,r in enumerate(rows[:3]):
            r.scroll_into_view_if_needed(); pg.wait_for_timeout(1600); r.screenshot(path=f'out/gs-row{i+1}-{name}.png')
        pg=b.new_page(viewport={'width':w,'height':900},device_scale_factor=sc)
        pg.on('pageerror',lambda e:print('PAGEERROR home',name,e))
        pg.goto(f'http://127.0.0.1:{port}/index.html'); pg.wait_for_timeout(3500)
        pg.query_selector('#hx-card').screenshot(path=f'out/home-card-{name}.png')
    b.close()
srv.shutdown()
