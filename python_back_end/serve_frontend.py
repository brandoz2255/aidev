from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class CORSRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super().end_headers()

def run_server(port=8000):
    # Change to the frontend directory
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'front_end')
    os.chdir(frontend_dir)
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, CORSRequestHandler)
    print(f"Serving frontend at http://localhost:{port}")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server() 