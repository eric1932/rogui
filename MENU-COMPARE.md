# 左侧菜单对照：原厂 / KoolCenter / 融合版

从三份 `menuTree.js` 静态解析得出，名称取自简体中文字典。

- 带 `*` 的项会按机型能力显示或隐藏，所以实际界面上看到的会少一些。
  - 例如原厂"仪表板"有新旧两个，只显示其中一个
  - UU 加速器、腾讯网游加速器、SMS 是国行机型或带 4G 模块的机型才有
- 实际显示的列表以浏览器 agent 抓取的结果为准，见 `BROWSER-TEST-PROMPT.md`

## 原厂 ROG（102_39441）

| # | 菜单 | 页数 | index |
|---|---|---|---|
| 1 |  网络设置向导 | 1 | `menu_QIS` |
| 2 |  ── 一般设置 ── |  | `menu_Split` |
| 3 |  仪表板 | 1 | `menu_Dashboard` |
| 4 | * AiMesh | 1 | `menu_AiMesh` |
| 5 | * 仪表板 | 1 | `menu_NewDashboard` |
| 6 | * AiProtection 网络神盾 | 6 | `menu_AiProtection` |
| 7 | * 家长管理 | 4 | `menu_ParentalControl` |
| 8 | * 电竞加速 | 7 | `menu_GameBoost` |
| 9 | * Open NAT | 1 | `menu_GameProfile` |
| 10 |  游戏探测雷达 | 1 | `menu_GameRadar` |
| 11 | * WiFi Radar（WiFi 雷达） | 1 | `menu_WifiRadar` |
| 12 | * VPN | 4 | `menu_VPN` |
| 13 | * Traffic Analyzer 流量分析 | 7 | `menu_TrafficAnalyzer` |
| 14 |  ── 高级设置 ── |  | `menu_Split` |
| 15 |  网络地图 | 1 | `menu_Index` |
| 16 | * 无线网络 | 9 | `menu_Wireless` |
| 17 | * ? | 4 | `menu_GuestNetwork` |
| 18 |  内部网络(LAN) | 8 | `menu_LAN` |
| 19 | * 外部网络(WAN) | 10 | `menu_WAN` |
| 20 | * USB 相关应用 | 8 | `menu_APP` |
| 21 | * AiCloud 2.0个人云 2.0 应用 | 5 | `menu_AiCloud` |
| 22 | * Alexa & IFTTT | 2 | `menu_Alexa_IFTTT` |
| 23 | * IPv6 | 2 | `menu_IPv6` |
| 24 | * 防火墙 | 4 | `menu_Firewall` |
| 25 |  系统管理 | 13 | `menu_Setting` |
| 26 |  系统记录 | 9 | `menu_Log` |
| 27 | * 网络工具 | 4 | `menu_NekworkTool` |

## KoolCenter 梅林改版（102.8_0）

| # | 菜单 | 页数 | index |
|---|---|---|---|
| 1 |  网络设置向导 | 1 | `menu_QIS` |
| 2 |  ── 一般设置 ── |  | `menu_Split` |
| 3 |  网络地图 | 1 | `menu_Index` |
| 4 | * AiMesh | 1 | `menu_AiMesh` |
| 5 | * ? | 4 | `menu_GuestNetwork` |
| 6 | * 仪表板 | 1 | `menu_NewDashboard` |
| 7 | * AiProtection 网络神盾 | 6 | `menu_AiProtection` |
| 8 | * 家长管理 | 6 | `menu_ParentalControl` |
| 9 | * Adaptive QoS 智能场景加速 | 9 | `menu_BandwidthMonitor` |
| 10 | * UU 加速器 | 1 | `menu_UU` |
| 11 | * Traffic Analyzer 流量分析 | 7 | `menu_TrafficAnalyzer` |
| 12 | * 游戏加速 | 1 | `menu_GameBoost` |
| 13 | * Open NAT | 1 | `menu_OpenNAT` |
| 14 | * 腾讯网游加速器 | 1 | `menu_TencentAcceleration` |
| 15 | * USB 相关应用 | 10 | `menu_APP` |
| 16 | * AiCloud 2.0个人云 2.0 应用 | 5 | `menu_AiCloud` |
| 17 |  System Info | 1 | `menu_Sysinfo` |
| 18 | * SMS | 2 | `menu_SMS` |
| 19 |  ── 高级设置 ── |  | `menu_Split` |
| 20 | * 无线网络 | 9 | `menu_Wireless` |
| 21 |  内部网络(LAN) | 9 | `menu_LAN` |
| 22 | * 外部网络(WAN) | 11 | `menu_WAN` |
| 23 | * Alexa & IFTTT | 2 | `menu_Alexa_IFTTT` |
| 24 | * IPv6 | 2 | `menu_IPv6` |
| 25 | * VPN | 10 | `menu_VPN` |
| 26 | * 防火墙 | 4 | `menu_Firewall` |
| 27 |  系统管理 | 15 | `menu_Setting` |
| 28 |  系统记录 | 9 | `menu_Log` |
| 29 | * 网络工具 | 5 | `menu_NekworkTool` |
| 30 |  ── koolshare - 软件中心 ── |  | `menu_Split` |
| 31 |  软件中心 | 2 | `menu_Softcenter` |

## 融合版（rogui，以原厂顺序为底）

| # | 菜单 | 页数 | index |
|---|---|---|---|
| 1 |  网络设置向导 | 1 | `menu_QIS` |
| 2 |  ── 一般设置 ── |  | `menu_Split` |
| 3 |  仪表板 | 1 | `menu_Dashboard` |
| 4 | * AiMesh | 1 | `menu_AiMesh` |
| 5 | * 仪表板 | 1 | `menu_NewDashboard` |
| 6 | * AiProtection 网络神盾 | 6 | `menu_AiProtection` |
| 7 | * 家长管理 | 4 | `menu_ParentalControl` |
| 8 | * 电竞加速 | 8 | `menu_GameBoost` |
| 9 | * Open NAT | 1 | `menu_GameProfile` |
| 10 |  游戏探测雷达 | 1 | `menu_GameRadar` |
| 11 | * WiFi Radar（WiFi 雷达） | 1 | `menu_WifiRadar` |
| 12 | * VPN | 10 | `menu_VPN` |
| 13 | * Traffic Analyzer 流量分析 | 9 | `menu_TrafficAnalyzer` |
| 14 |  ── 高级设置 ── |  | `menu_Split` |
| 15 |  网络地图 | 1 | `menu_Index` |
| 16 | * 无线网络 | 9 | `menu_Wireless` |
| 17 | * ? | 4 | `menu_GuestNetwork` |
| 18 |  内部网络(LAN) | 9 | `menu_LAN` |
| 19 | * 外部网络(WAN) | 10 | `menu_WAN` |
| 20 | * USB 相关应用 | 8 | `menu_APP` |
| 21 | * AiCloud 2.0个人云 2.0 应用 | 5 | `menu_AiCloud` |
| 22 | * Alexa & IFTTT | 2 | `menu_Alexa_IFTTT` |
| 23 | * IPv6 | 2 | `menu_IPv6` |
| 24 | * 防火墙 | 4 | `menu_Firewall` |
| 25 |  系统管理 | 14 | `menu_Setting` |
| 26 |  系统记录 | 9 | `menu_Log` |
| 27 | * 网络工具 | 5 | `menu_NekworkTool` |
| 28 |  System Info | 1 | `menu_Sysinfo` |
| 29 |  ── koolshare - 软件中心 ── |  | `menu_Split` |
| 30 |  软件中心 | 2 | `menu_Softcenter` |

## 差异摘要

### 顺序
- **原厂**：一般设置里依次是仪表板、AiMesh、网络神盾、家长管理、电竞加速、Open NAT、游戏雷达、WiFi 雷达、VPN、流量分析；高级设置从网络地图开始
- **KoolCenter**：网络地图放在一般设置第一项，VPN 挪到高级设置，Adaptive QoS 单独成一个菜单
- **融合版**：沿用**原厂顺序**，不是 KoolCenter 的顺序。Merlin 的页面插进原厂对应的菜单里；System Info 和软件中心放在最后

### 原厂有、KoolCenter 没有（融合版补回来了）
- 仪表板（Game Dashboard）
- 电竞加速里的 WTFast、设备加速器（Gear Accelerator）
- 游戏探测雷达
- WiFi Radar（WiFi 雷达）

### KoolCenter 有、原厂没有（融合版也加了）
- VPN：VPN Status、VPN Director、OpenVPN 服务器和客户端、WireGuard、GRE（整块换成 Merlin 版）
- 电竞加速：Classification（QoS 分类统计）
- 流量分析：流量月报、Traffic Monitor 设置
- 内部网络：DNS Director
- 系统管理：Tweaks（Tools_OtherSettings）
- 网络工具：Site Survey
- System Info（Sysinfo）
- 软件中心

### KoolCenter 有、融合版没有
- 大多是按机型隐藏的项，这台机器在 KoolCenter 界面里本来也看不到：
  - UU 加速器、腾讯网游加速器、腾讯下载加速
  - SMS
  - VDSL、OAM（DSL 机型才有）
  - 网页与 Apps 过滤、网页浏览历史（其他机型的家长管理页）
- NFS Exports：Merlin 说明 Wi-Fi 7 机型不支持 NFS
- Spectrum（Main_Spectrum_Content）：没有加
- KoolCenter 的 Adaptive QoS 菜单：原厂的同类页面在"电竞加速"里
