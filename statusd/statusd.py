import json
from http.server import HTTPServer, BaseHTTPRequestHandler


def stats():
    with open("/proc/loadavg") as f:
        load = float(f.read().split()[0])

    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split()[0], int(line.split()[1])
            if key in ("MemTotal:", "MemAvailable:"):
                mem[key] = val
    mem_pct = round(100 * (1 - mem["MemAvailable:"] / mem["MemTotal:"]))

    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = round(int(f.read()) / 1000, 1)
    except OSError:
        temp = None

    with open("/proc/uptime") as f:
        uptime_s = int(float(f.read().split()[0]))
    uptime_h = uptime_s // 3600

    return {"load": load, "mem_pct": mem_pct, "temp": temp, "uptime_h": uptime_h}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(stats()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
