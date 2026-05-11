import os
import platform
import sys
import time

import akshare as ak

print("python:", sys.version)
print("platform:", platform.platform())
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    print(f"{key}={os.environ.get(key)}")

start = time.time()
try:
    df = ak.stock_zh_a_spot_em()
    print("spot_ok:", df.shape, "elapsed:", round(time.time() - start, 2))
except Exception as exc:
    print("spot_err:", repr(exc), "elapsed:", round(time.time() - start, 2))
