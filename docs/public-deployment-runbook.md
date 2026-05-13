# Public Deployment Runbook

## 1. Server

Recommended baseline:
- Ubuntu 22.04
- 2 vCPU
- 4 GB RAM

## 2. Upload Project

Clone the repo on the server:

```bash
git clone <your-repo-url> Ashare
cd Ashare
```

## 3. Create Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r akshare_backend/requirements.txt
```

## 4. Set Environment Variables

Create a local `.env` file or export variables directly:

```bash
export ASHARE_HOST=0.0.0.0
export ASHARE_PORT=5000
export ASHARE_DEBUG=0

export TUSHARE_TOKEN="your_tushare_token"
export TUSHARE_HTTP_URL="http://124.220.22.110:8020/"

export DEEPSEEK_API_KEY="your_deepseek_api_key"
export DEEPSEEK_BASE_URL="https://oapio.zeabur.app/v1"
export DEEPSEEK_MODEL="deepseek-v4-flash"
export DEEPSEEK_REASONING_EFFORT="minimal"
export DEEPSEEK_THINKING_TYPE="disabled"
export DEEPSEEK_TIMEOUT_SECONDS="90"
```

## 5. First Boot

```bash
python akshare_backend/start_server.py
```

Then test:

```bash
curl http://127.0.0.1:5000/api/health
```

Expected:

```json
{"status":"ok","message":"Ashare backend is ready."}
```

## 6. Production Start Recommendation

For the first public version, use a process manager or service wrapper.

If you want to keep it simple:
- run the app in `tmux` or `screen`

Better:
- use `systemd`

Optional later:
- switch to `waitress` or `gunicorn`

## 7. Nginx Reverse Proxy

Basic example:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 8. HTTPS

After the domain resolves correctly, add HTTPS with Certbot:

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## 9. Data Directories

Keep these writable:
- `result/`
- `result/userdata/`

These directories currently hold:
- exported files
- cached market results
- holdings drafts
- operations drafts

## 10. Important Limitation Before Wider Sharing

Current drafts are shared globally on the server.

So before giving this to more friends, we should add at least one of:
- a simple password gate
- lightweight user/session separation

For 2 to 3 people testing, current state is still usable.

## 11. Recommended Rollout Order

1. Deploy to one server
2. Test yourself remotely
3. Let 1 to 2 friends try it
4. Fix obvious issues
5. Then open it to the full small group
