# SuperHaojun 阿里云部署指南

> 先看这一条：
>
> 如果你是把 `SuperHaojun` 作为 `personal-web` 的子模块一起上线，请不要直接部署本仓库。
> 那种场景应该部署 `personal-web`，并由 `personal-web/apps/superhaojun` 引用本仓库。
>
> 本文档只适用于“独立部署 SuperHaojun WebUI / Harness”。

这份文档给你一条尽量精简、稳定、适合当前项目结构的部署方案：

- 平台：阿里云 ECS
- 系统：Ubuntu 24.04 LTS
- 进程管理：`systemd`
- 反向代理：`nginx`
- HTTPS：Let's Encrypt + Certbot

适合当前仓库，因为它本身就是：

- FastAPI 后端
- WebSocket
- WebUI 静态资源内置到 `src/superhaojun/webui/static/`
- 依赖本地 `.env`、`models.yaml`、`.haojun/`

如果你准备先把第一个可用版本稳定上线，这条路线最省心。

## 适用范围

这份文档适合下面这种情况：

- 你要把 `SuperHaojun` 当成一个独立产品部署
- 你希望直接访问 `SuperHaojun WebUI`
- 你的服务器只负责这一个 harness 服务

这份文档不适合下面这种情况：

- 你的网站正式入口是 `personal-web`
- `SuperHaojun` 只是 `personal-web/apps/superhaojun` 的 submodule
- 你最终对外部署的是网站，而不是单独的 harness 仓库

## 一、推荐配置

建议第一台服务器直接选：

- 2 vCPU
- 4 GB 内存
- 40 GB 以上系统盘
- Ubuntu 24.04

域名建议先用二级域名，例如：

- `agent.yourdomain.com`

这样后面切主域名更灵活。

## 二、部署前准备

你需要先准备好：

1. 阿里云 ECS 一台
2. 一个域名或子域名
3. 本地 SSH 公钥
4. 本地这些配置文件
   - `.env`
   - `models.yaml`
   - 如果要保留运行态，再带上 `.haojun/`

## 三、购买并初始化 ECS

在阿里云控制台创建 ECS 时，建议：

- 镜像选 `Ubuntu 24.04`
- 登录方式选 `密钥对`
- 公网 IP 打开
- 带宽按你预算选一个基础值即可

实例创建完成后，记下公网 IP。

## 四、配置安全组

安全组入方向只放行：

- `22`：SSH
- `80`：HTTP
- `443`：HTTPS

出方向保持允许全部即可。

如果你想更稳一点：

- `22` 端口只放行你自己的办公 IP

## 五、配置域名解析

给域名加一条 A 记录：

- 主机记录：`agent`
- 记录值：你的 ECS 公网 IP

如果你用主域名，就直接把根域名指向服务器 IP。

等解析生效后再申请 HTTPS。

## 六、登录服务器并创建部署用户

先用 root 登录：

```bash
ssh root@你的服务器IP
```

创建一个专门部署的用户：

```bash
adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

然后重新登录：

```bash
ssh deploy@你的服务器IP
```

## 七、安装基础环境

先装系统依赖：

```bash
sudo apt update
sudo apt install -y git curl unzip build-essential nginx python3 python3-venv ca-certificates
```

安装 Node.js 20：

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

安装 `uv`：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

确认版本：

```bash
node -v
npm -v
uv --version
python3 --version
```

## 八、拉取代码

建议统一放到 `/srv`：

```bash
sudo mkdir -p /srv
sudo chown deploy:deploy /srv
cd /srv
git clone git@github.com:YOUR_USERNAME/superhaojun.git
cd superhaojun
```

如果你用 HTTPS 拉代码，也可以：

```bash
git clone https://github.com/YOUR_USERNAME/superhaojun.git
```

## 九、上传生产配置

先把生产环境的 `.env` 放进去：

```bash
nano /srv/superhaojun/.env
```

最少要有：

```env
OPENROUTER_API_KEY=你的真实Key
```

然后检查 `models.yaml`。

当前更推荐的默认模型是：

- `gpt-oss-120b-free`

如果你后面换成付费模型，也是在这里改。

如果你要保留本地运行态，可以把 `.haojun/` 一起传上去：

```bash
scp -r /本地路径/.haojun deploy@你的服务器IP:/srv/superhaojun/
```

注意：

- `.env` 不要提交到 GitHub
- `.haojun/` 也不要提交

## 十、安装 Python 依赖

进入项目目录：

```bash
cd /srv/superhaojun
uv sync
```

## 十一、构建前端

因为 WebUI 最终是由 FastAPI 直接托管静态资源，所以要先构建：

```bash
cd /srv/superhaojun/webui
npm ci
npm run build
```

构建产物会进入：

- `src/superhaojun/webui/static/`

## 十二、创建 systemd 服务

新建服务文件：

```bash
sudo nano /etc/systemd/system/superhaojun-web.service
```

填入：

```ini
[Unit]
Description=SuperHaojun WebUI
After=network.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/srv/superhaojun
Environment=HOME=/home/deploy
Environment=PATH=/home/deploy/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=SUPERHAOJUN_PORT=8765
ExecStart=/home/deploy/.local/bin/uv run superhaojun-web
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable superhaojun-web
sudo systemctl start superhaojun-web
```

检查状态：

```bash
sudo systemctl status superhaojun-web
journalctl -u superhaojun-web -n 100 --no-pager
```

本机验证：

```bash
curl http://127.0.0.1:8765/api/config
```

如果这里通了，说明应用已经正常启动。

## 十三、配置 Nginx

创建配置文件：

```bash
sudo nano /etc/nginx/sites-available/superhaojun
```

填入，把域名换成你的：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name agent.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/superhaojun /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

现在访问：

- `http://agent.yourdomain.com`

应该已经能打开页面。

## 十四、配置 HTTPS

安装 Certbot：

```bash
sudo snap install core
sudo snap refresh core
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot
```

申请证书：

```bash
sudo certbot --nginx -d agent.yourdomain.com
```

建议选择：

- 自动跳转到 HTTPS

然后测试自动续期：

```bash
sudo certbot renew --dry-run
```

## 十五、上线后检查

依次检查：

```bash
curl -I http://agent.yourdomain.com
curl -I https://agent.yourdomain.com
curl https://agent.yourdomain.com/api/config
```

浏览器里重点看：

1. 首页能否打开
2. WebSocket 是否正常
3. Settings 是否能读到模型列表
4. approval modal 是否能弹出
5. context 面板是否会更新

## 十六、后续更新流程

以后每次更新就按这个顺序：

```bash
cd /srv/superhaojun
git pull
uv sync
cd webui
npm ci
npm run build
cd ..
sudo systemctl restart superhaojun-web
sudo systemctl status superhaojun-web
```

## 十七、常用排障命令

看应用日志：

```bash
journalctl -u superhaojun-web -f
```

看 Nginx 日志：

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

看服务状态：

```bash
sudo systemctl status superhaojun-web
sudo systemctl status nginx
```

看本机接口：

```bash
curl http://127.0.0.1:8765/api/runtime
```

## 十八、建议备份的文件

至少备份这几个：

- `/srv/superhaojun/.env`
- `/srv/superhaojun/models.yaml`
- `/srv/superhaojun/.haojun/`

原因很简单：

- `.env` 是密钥
- `models.yaml` 是模型配置
- `.haojun/` 里可能有 session、memory、开关状态等运行态数据

## 十九、当前这套部署的注意点

- OpenRouter 免费模型会波动，可能偶发 `404` 或 `429`
- 当前默认模型选的是这轮验证里真实跑通过普通对话和 approval 流程的 profile
- 如果后面某个模型不稳定，直接改 `models.yaml` 然后重启服务即可
- Nginx 里的 WebSocket 头不要删，否则前端实时能力会出问题

## 参考资料

- [阿里云 ECS 概述](https://help.aliyun.com/zh/ecs/user-guide/instance-lifecycle)
- [阿里云安全组规则](https://help.aliyun.com/zh/ecs/use-cases/security-group-quintuple-rules)
- [阿里云云解析 DNS](https://help.aliyun.com/zh/dns/)
- [Certbot 官方](https://certbot.eff.org/)
