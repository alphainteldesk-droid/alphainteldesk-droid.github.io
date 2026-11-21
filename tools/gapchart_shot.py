# Throwaway test helper (branch gapchart-test only): screenshots + a short clip of the Live Gap Chart.
import threading, http.server, socketserver, os, subprocess
from playwright.sync_api import sync_playwright
root=os.getcwd(); os.makedirs('out/frames',exist_ok=True)
class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(s,*a,**k): super().__init__(*a,directory=root,**k)
    def log_message(self,*a): pass
srv=socketserver.TCPServer(('127.0.0.1',0),Q); port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,name in ((1440,'desktop'),(390,'phone')):
        pg=b.new_page(viewport={'width':w,'height':900},device_scale_factor=1 if w>500 else 2)
        pg.on('pageerror',lambda e:print('PAGEERROR',e))
        pg.goto(f'http://127.0.0.1:{port}/gap-scanner.html'); pg.wait_for_timeout(4000)
        el=pg.query_selector('#gapchart'); el.screenshot(path=f'out/gapchart-{name}.png')
        if name=='desktop':
            for i in range(150):
                el.screenshot(path='out/frames/f%03d.png'%i); pg.wait_for_timeout(40)
    b.close()
srv.shutdown()
subprocess.run('ffmpeg -y -loglevel error -framerate 25 -i out/frames/f%03d.png -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p out/gapchart-desktop.mp4',shell=True)
subprocess.run('rm -rf out/frames',shell=True)
