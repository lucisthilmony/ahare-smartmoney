#!/bin/bash
# 打印 Tushare 原始返回的 code/msg，定位是 token 无效还是积分不足。结果写入 token测试结果.txt。
cd "$(dirname "$0")"
./.venv/bin/python - > token测试结果.txt 2>&1 <<'PY'
import os, json
os.environ["NO_PROXY"]="*"; os.environ["no_proxy"]="*"
import requests, config as C
tok = C.TUSHARE_TOKEN
print("token 前6位/后4位:", tok[:6]+"..."+tok[-4:], " 长度", len(tok))
for api in ("stock_basic", "trade_cal"):
    payload = {"api_name": api, "token": tok,
               "params": ({"list_status":"L"} if api=="stock_basic" else {"exchange":"SSE","start_date":"20260601","end_date":"20260620"}),
               "fields": ""}
    try:
        r = requests.post("https://api.tushare.pro", json=payload, timeout=15)
        j = r.json()
        items = (j.get("data") or {}).get("items") or []
        print(f"[{api}] HTTP {r.status_code} | code={j.get('code')} | msg={j.get('msg')!r} | 行数={len(items)}")
    except Exception as e:
        print(f"[{api}] 请求异常: {str(e)[:160]}")
print("=== 结束 ===")
PY
echo "结果已写入 token测试结果.txt"
