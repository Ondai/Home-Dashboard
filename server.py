import http.server
import socketserver
import subprocess
import json
import os

PORT = 8000

class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/update':
            try:
                # Run git pull
                # We use shell=False for security, assuming 'git' is in PATH
                result = subprocess.run(['git', 'pull'], capture_output=True, text=True)
                
                success = result.returncode == 0
                output = result.stdout
                error = result.stderr
                
                response_data = {
                    'success': success,
                    'output': output,
                    'error': error
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
        else:
            self.send_error(404)

if __name__ == "__main__":
    # Allow reusing the address to prevent 'Address already in use' errors on restart
    socketserver.TCPServer.allow_reuse_address = True
    
    with socketserver.TCPServer(("", PORT), DashboardRequestHandler) as httpd:
        print(f"Serving dashboard at http://localhost:{PORT}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
