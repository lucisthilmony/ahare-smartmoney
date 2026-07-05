# -*- coding: utf-8 -*-
"""
A股短线波段操作助手 · 本地数据服务
启动后：
  - 浏览器打开 http://127.0.0.1:8787/  即用（推荐，功能最全）
  - 或继续双击 .html 离线打开（读 data.js，盘中实时不可用）
接口：
  GET /                 → 操作助手页面
  GET /data.js          → 最新盘后数据（HTML 离线也读它）
  GET /api/eod          → 最新盘后数据(JSON)：市场状态 + 候选池
  GET /api/refresh      → 重新拉数据并刷新（盘后定时任务调它）
  GET /api/quote?codes=600000,300750 → 盘中实时(新浪L1)：现价/今开/高开%/涨幅%
不替你下单。
"""
import os, json, traceback
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import config as C
import pipeline as P

app = Flask(__name__)
CORS(app)  # 允许 file:// 页面跨域调用本机服务
LATEST = {"data": None}

def _load_cached():
    try:
        if os.path.exists(C.DATA_JS_PATH):
            txt = open(C.DATA_JS_PATH, encoding="utf-8").read()
            s = txt.find("{"); e = txt.rfind("}")
            if s >= 0 and e > s:
                LATEST["data"] = json.loads(txt[s:e+1])
    except Exception as ex:
        print("[warn] 读取缓存 data.js 失败：", ex)

@app.route("/")
def home():
    return send_from_directory(C.BASE_DIR, C.HTML_NAME)

@app.route("/data.js")
def data_js():
    if os.path.exists(C.DATA_JS_PATH):
        return send_from_directory(C.BASE_DIR, "data.js", mimetype="application/javascript")
    return Response("window.STRATEGY_DATA=null;", mimetype="application/javascript")

@app.route("/api/eod")
def api_eod():
    _load_cached()  # 每次都重读 data.js：定时任务直接重写文件后也能立即生效
    return jsonify(LATEST["data"] or {"error": "暂无数据，请先 /api/refresh 或运行 pipeline.py"})

@app.route("/api/refresh")
def api_refresh():
    try:
        data = P.build_data()
        P.write_data_js(data)
        LATEST["data"] = data
        return jsonify({"ok": True, "date": data["date"],
                        "data_date": data.get("data_date"), "is_fresh": data.get("is_fresh"),
                        "source": data["source"],
                        "tier": data["state"]["tier"], "cap": data["state"]["cap"],
                        "candidates": len(data["candidates"])})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex), "trace": traceback.format_exc()}), 500

@app.route("/api/quote")
def api_quote():
    codes = [c for c in request.args.get("codes", "").split(",") if c.strip()]
    if not codes:
        return jsonify({"error": "缺少 codes 参数"})
    return jsonify(P.realtime_sina(codes))

@app.route("/api/market")
def api_market():
    return jsonify(P.realtime_market())

@app.route("/api/flow")
def api_flow():
    return jsonify(P.realtime_flow())

if __name__ == "__main__":
    _load_cached()
    print("=" * 56)
    print(" A股短线波段 · 数据服务已启动")
    print(" 浏览器打开： http://%s:%d/" % (C.SERVER_HOST, C.SERVER_PORT))
    print(" 盘后刷新数据： http://%s:%d/api/refresh" % (C.SERVER_HOST, C.SERVER_PORT))
    print(" 关闭：在本窗口按 Control+C")
    print("=" * 56)
    app.run(host=C.SERVER_HOST, port=C.SERVER_PORT, debug=False)
