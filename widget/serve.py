"""RAGForgeWidget 演示静态服务。

Windows 下 `python -m http.server` 可能把 .js 注册为 text/plain
（与 src/ragforge/api/app.py 处理的是同一个注册表问题），
本脚本显式修正 MIME 后启动，避免浏览器按错误类型加载挂件脚本。

用法:
    python serve.py [端口]      # 默认 8080 → http://localhost:8080/demo.html
"""

import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class _Handler(SimpleHTTPRequestHandler):
    """Add explicit charset so browsers decode UTF-8 pages correctly."""

    def guess_type(self, path):
        ctype = super().guess_type(path)
        if ctype.startswith("text/") and "charset=" not in ctype:
            ctype += "; charset=utf-8"
        return ctype


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"演示页地址: http://localhost:{port}/demo.html  (Ctrl+C 停止)")
    ThreadingHTTPServer(("127.0.0.1", port), _Handler).serve_forever()
