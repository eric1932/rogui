# 菜单对照：原厂、KoolCenter、rogui

rogui 的左侧菜单以原厂 ROG 菜单为底，原厂的菜单项都在，再按下面几节增减。对照的是原厂 102_39441 和 KoolCenter 102.8_0 的 `menuTree.js`。有些菜单项按机型显示或隐藏，下面只列 GT-BE98 Pro 上真有区别的。

## 顺序

- **原厂**：一般设置里依次是仪表板、AiMesh、网络神盾、家长管理、电竞加速、Open NAT、游戏雷达、WiFi 雷达、VPN、流量分析；高级设置从网络地图开始。
- **KoolCenter**：网络地图是一般设置的第一项，VPN 挪到高级设置，Adaptive QoS 单独成一个菜单。
- **rogui**：沿用原厂的顺序，最后加上 System Info 和软件中心。

## 从 KoolCenter 加进来的页面

| 放在哪个菜单 | 加的页面 |
|---|---|
| VPN | 整块换成 Merlin 版：VPN Status、VPN Director、OpenVPN 和 WireGuard 的客户端与服务器 |
| 电竞加速 | Classification（QoS 分类统计） |
| 流量分析 | 流量月报、Traffic Monitor 设置 |
| 内部网络 | DNS Director |
| 系统管理 | Tweaks |
| 网络工具 | Site Survey |
| 菜单最后 | System Info、软件中心 |

## 原厂有、rogui 没有的

- VPN Fusion 视图：换成了上表里的 Merlin VPN 页面。
- 6GHz AFC、天线灯、Instant Guard 站点互联：GT-BE98 Pro 的原厂 httpd 里也没有对应接口，不是 rogui 去掉的。

## KoolCenter 有、rogui 没有的

- 按机型隐藏的项，在这台机器的 KoolCenter 界面里本来也看不到：UU 加速器、腾讯网游加速器、腾讯下载加速、SMS、VDSL 和 OAM（DSL 机型才有）、网页与 Apps 过滤和网页浏览历史（其他机型的家长管理页）。
- NFS Exports：Merlin 说明 Wi-Fi 7 机型不支持 NFS。
- Spectrum：KoolCenter 固件里没有这个页面。
- Adaptive QoS 菜单：原厂的同类页面在「电竞加速」里。
