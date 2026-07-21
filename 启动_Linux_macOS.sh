#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装 Python 3.10+。"
  exit 1
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
PORT=$(python - <<'EOF'
import socket
s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()
EOF
)
echo "浏览器地址：http://127.0.0.1:${PORT}"
python -m streamlit run app.py --server.address 127.0.0.1 --server.port "$PORT" --server.headless true --browser.gatherUsageStats false
