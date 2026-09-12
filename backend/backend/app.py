from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os

from market_data import MarketData
from smc_analyzer import SMCAnalyzer

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/analyze", methods=["GET"])
def analyze():
    symbol = request.args.get("symbol", "BTC-USD")
    timeframe = request.args.get("timeframe", "1h")
    limit = int(request.args.get("limit", 500))
    try:
        df = MarketData.get_ohlc(symbol, timeframe, limit)
        analyzer = SMCAnalyzer(df)
        result = analyzer.analyze()
        return jsonify({"success": True, "symbol": symbol, "timeframe": timeframe, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
