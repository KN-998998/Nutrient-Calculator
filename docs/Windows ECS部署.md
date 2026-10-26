# Windows ECS 部署

## 运行方式

服务器部署使用 Waitress，不使用 Flask 开发服务器。默认监听：

```text
0.0.0.0:8300
```

桌面版仍然使用 `desktop_app/app.py` 的本机浏览器模式和默认端口 8317，部署入口不会改变桌面版行为。

## 首次安装

在 ECS 的项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 注册开机启动和异常重启

使用管理员 PowerShell 执行：

```powershell
.\scripts\install_windows_task.ps1
```

该脚本注册名为 `NutrientCalculator` 的 SYSTEM 任务，开机启动服务；服务异常退出时最多自动重启 3 次。运行日志写入：

```text
logs\web.log
```

## 验证

先验证本机健康检查和监听端口：

```powershell
Invoke-RestMethod http://127.0.0.1:8300/healthz
Get-NetTCPConnection -LocalPort 8300 -State Listen
Get-ScheduledTask -TaskName NutrientCalculator
```

预期健康检查返回：

```json
{"status":"ok"}
```

再从另一台机器访问：

```text
http://<ECS公网IP>:8300/
```

阿里云安全组放行 8300 只是网络层条件，还需要同时确认 ECS 本机 Windows 防火墙、任务状态、监听地址和公网路由。当前应用没有登录认证或 HTTPS；如果 8300 对公网开放，只适合受控测试环境，正式使用前应限制安全组来源 IP，或增加认证和 HTTPS 反向代理。

## 更新代码

更新代码并重新安装依赖后，重启任务：

```powershell
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Restart-ScheduledTask -TaskName NutrientCalculator
Invoke-RestMethod http://127.0.0.1:8300/healthz
```

不要在未确认工作树干净、远程分支和备份策略前执行覆盖式回滚或删除操作。
