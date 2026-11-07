# 上机测试清单（rogui 启用后）

开始前：浏览器**退出登录再重新登录**一次（state.js 会在 sessionStorage 里缓存菜单）。
有问题随时执行 `ssh admin@192.168.50.1 'sh /jffs/rogui/rogui.sh stop'`，或者直接重启路由器。

按风险从高到低（来自 `research/reports/04-www-compat-audit.md`）：

| # | 页面 | 看什么 | 结果 |
|---|---|---|---|
| 1 | 登录页 Main_Login.asp | 能登录，验证码正常 | |
| 2 | Dashboard（GameDashboard.asp） | 页面能加载；灯效能改；网速、WAN 状态显示 | |
| 3 | 网络地图 index.asp | 设备列表、路由器面板 | |
| 4 | System Info → Sysinfo；系统管理 → Tweaks | Merlin 页面，文字没有错乱（验证字典重映射） | |
| 5 | 软件中心 | 菜单在最后一项、ROG 皮、插件列表能加载 | |
| 6 | 无线 → 常规 | **保存一次**，确认能保存、WiFi 正常 | |
| 7 | 外部网络 WAN | DNS / DoT 设置显示正确 | |
| 8 | VPN → VPN Director / OpenVPN 客户端 | Merlin 版页面能打开 | |
| 9 | 游戏加速 / QoS | 显示是否正常（Merlin 的 Cake 原厂页面认不出） | |
| 10 | 访客网络 Pro / MLO | 能打开 | |
| 11 | AiMesh | 能打开 | |
| 12 | 系统管理 → 固件升级、恢复/导出设置 | **只看不点**：不要在线升级；不要导入原厂 .CFG | |

另外两项：
- QoS → Classification、网络工具 → Site Survey：这两页依赖 build.py 补进去的函数
- 流量分析 → 月报（Main_TrafficMonitor_monthly）
