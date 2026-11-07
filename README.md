# rogui：GT-BE98 Pro 刷 KoolCenter 梅林改版后换回原厂 ROG 界面

> **English:** rogui puts ASUS's stock ROG web UI back on a GT-BE98 Pro running the KoolCenter build of Asuswrt-Merlin (3006.102), while keeping the Merlin pages (VPN Director, DNS Director, Tweaks, Sysinfo…) and the KoolCenter Software Center. Only the web layer is replaced. The overlay is built on your computer from the two firmware files you already have. There are two ways to deliver it: **overlay mode** (default) bind-mounts it over `/www` at boot and leaves the firmware untouched; **baked mode** (experimental) bakes the merged web UI into the KoolCenter firmware image, so nothing is kept in jffs. Docs are in Chinese.

<!-- 截图：首页、软件中心、一个 Merlin 页面（如 VPN Director）。放到 docs/ 下再在这里引用 -->

KoolCenter 梅林改版（3006.102 分支）没有 ROG 皮肤，界面是普通的蓝色华硕界面。rogui 在开机时把原厂 ROG 网页盖到 `/www` 上：
- 菜单沿用原厂的顺序，Merlin 的页面插进原厂对应的菜单里，System Info 和软件中心放在最后；
- 原厂有、KoolCenter 界面里没有的页面也回来了：Game Dashboard、游戏探测雷达、WiFi 雷达、WTFast、设备加速器；
- 软件中心照常可用，皮肤自动切成 ROG 版。

只换网页层：httpd、rc、软件中心后端都还是 KoolCenter 的。有两种方案，出来的网页完全一样：

| | 挂载版（overlay，默认） | 固件版（baked，实验性） |
|---|---|---|
| 做法 | 开机时把补丁包盖到 `/www` 上，固件不动 | 把合好的网页做进 KoolCenter 固件，刷这个固件 |
| jffs 占用 | 约 13MB | 不到 10KB |
| 内存和开机时间 | 约 45MB，开机多约 2 秒 | 不额外占 |
| 撤回 | `rogui.sh stop`，马上变回蓝色 | 刷回 KoolCenter 原版固件 |

下面的「安装」「日常」讲的是挂载版，固件版见「固件版」一节。

## 需要

- **GT-BE98 Pro**（固件里的型号是 `GT-BE98_PRO`；不带 Pro 的 GT-BE98 不行），已经刷了 KoolCenter 梅林改版。测过 102.7_2 和 102.8_0。
- 路由器开了 ssh，jffs 自定义脚本开着（KoolCenter 默认开）。
- 电脑上有 `bash` 和 `python3`，只用标准库，不用装别的东西。在 macOS 上测过；Windows 可以试 WSL，没测过。
- 本目录下放两个固件文件：
  - 你刷的那版 KoolCenter 固件 `.pkgtb`；
  - 华硕官网 GT-BE98 Pro 支持页下载的原厂固件 `FW_GT-BE98_Pro_*.zip`，用来提取 ROG 网页，取最新的。

## 安装

首次安装和每次升级 KoolCenter 固件之后，都是这两步。`admin@192.168.50.1` 换成你的管理员账号和路由器地址。

```sh
ROUTER=admin@192.168.50.1 rogui/update.sh <KoolCenter 固件.pkgtb>
cat rogui/dist/rogui-<版本>.tgz | ssh admin@192.168.50.1 'tar xzf - -C /jffs && sh /jffs/rogui/rogui.sh install'
```

1. 第一行在电脑上打包，大约 30 秒，不碰路由器，可以在刷机之前做。
   - 显示 ✅ 时会打印第二行的完整命令，复制去跑；
   - 显示 ⚠️ 时**不要部署**，失败的包和检查报告在 `rogui/dist/failed/`。
2. 第二行把包解到 `/jffs/rogui/`，在 `/jffs/scripts/services-start` 加一行开机自启、在 `service-event-end` 加一行补回钩子，然后启用。重复执行没有影响。最后一行应该是 `已启用 ROG 网页`。
3. 浏览器按 Cmd+Shift+R（Windows 是 Ctrl+F5）强制刷新：路由器给 CSS 设了 1 小时缓存。左侧菜单如果没变，退出再登录一次。

## 日常

开机自动启用，不用管。

```sh
sh /jffs/rogui/rogui.sh status      # 看状态
sh /jffs/rogui/rogui.sh stop        # 立刻回到蓝色界面（重启后会再启用）
touch /jffs/rogui/disable           # 开机不再启用；删掉这个文件即恢复
sh /jffs/rogui/rogui.sh uninstall   # 去掉开机自启和钩子，并停用
```

界面突然变回蓝色，说明固件和补丁包不配套，多半是升级了固件但还没重新打包。按「安装」的两步重新做一遍即可，不会坏。

## 注意

- 补丁包只对**一版** KoolCenter 固件有效。路由器开机时会比对固件自带 `/www` 的指纹，对不上就跳过，保持蓝色界面。
- 不要用网页上的「检查更新」或在线升级：KoolCenter 换进来的是原厂的检查脚本，会拿原厂版本号比对，可能引导你刷回原厂。升级请手动上传固件。
- 不要导入原厂固件导出的 `.CFG` 配置文件：导入会绕过 httpd 的 nvram 白名单。
- 占用（挂载版）：jffs 约 13MB，内存约 45MB，开机多约 2 秒。固件版 jffs 不到 10KB，内存和开机时间都不额外占（见「固件版」）。
- 软件中心里有 8 个老插件（aliddns、cfddns、frpc、fastd1ck、qiandao、pushplus、routerhook、serverchan），如果是在启用 rogui 之前装的，要重装才会有 ROG 样式。

## 固件版：把 ROG 网页做进固件（可选，实验性）

挂载版要在 jffs 里放 13MB 的补丁包，开机时再复制一份网页到内存。固件版把合成好的网页直接做进 KoolCenter 固件，刷一个自带 ROG 网页的固件：jffs 里只剩 `rogui.sh`（不到 10KB），开机不用复制和挂载。代价是每次换固件都要重新做一次，界面坏了要刷回原版固件才能撤。

- 做法：只换固件根文件系统里的 `/www`，用和原包相同的参数重新打包 squashfs，再改 FIT 头里根文件系统那一段的大小和 sha256。KoolCenter 和原厂的 `.pkgtb` 都没有签名，只有 sha256。
- `bake.sh` 会把产物重新拆开，和原包逐项对比：`/www` 以外每个文件、目录、链接、设备文件的内容、权限、属主、修改时间都要相同，`/www` 要正好等于「原版 + 补丁包」，用另一个读取器（`sqfs.py`）直接读新固件也要得到同样的 `/www`。全部通过才产出固件。同样的输入总是打出逐字节相同的固件。
- 新固件的根文件系统比原版大约 8MB（102.8_0：60MB → 68MB）。

固件包的结构，以及做进固件时改了哪些地方：

```
KoolCenter .pkgtb
├─ FIT 包头（964 字节）    记着每段的位置、大小、sha256       ← 只改 rootfs 段的大小和 sha256
├─ bootfs 段（12.7MB）     ATF、U-Boot、内核、设备树           ← 一个字节不动
└─ rootfs 段（squashfs）   /bin /lib /usr /rom …              ← /www 以外逐项相同
                           /www                               ← 换成「原版 + 补丁包」，整个 squashfs 用原参数重打
```

刷机时新固件写进路由器闪存里没在用的那个号位（每个号位是一组 bootfs + rootfs），jffs、设置和插件都不动。

步骤：

1. 照「安装」第一步打好补丁包。
2. 做固件，三选一：
   - Linux：`sudo rogui/bake.sh <KoolCenter 固件.pkgtb> rogui/dist/rogui-<版本>.tgz`
   - macOS 装了 Docker：`rogui/bake-docker.sh <KoolCenter 固件.pkgtb> rogui/dist/rogui-<版本>.tgz`（两个文件都要在仓库目录里）
   - GitHub Actions：fork 本仓库，在 fork 里跑 `rogui/ci.sh run <KoolCenter 固件.pkgtb> [原厂固件.zip]`。它把固件传到草稿 Release「inputs」，触发 `bake` workflow，等跑完把产物下载到 `rogui/dist/ci-<编号>/`。草稿 Release 只有你自己看得到；**不要发布它**，发布就等于公开分发固件。CI 会重新打一个补丁包，里面文件的修改时间是打包那一刻，所以它做出的固件和你本地做的 sha256 不同，这是正常的。想核对的话，拿 CI 的补丁包在本地再做一次固件，sha256 应该和 CI 的相同。
3. 网页上「系统管理 → 固件升级」，手动上传产出的 `*-rogui-*.pkgtb`。
4. 刷好后照「安装」第二步再部署一次补丁包。`rogui.sh` 会认出固件自带 ROG 网页：不挂载，只补 `rc_support` 里的 `rog`，服务事件钩子照常。`rogui.sh status` 应显示「挂载: 不需要（固件自带 ROG 网页）」。确认没问题后可以删掉 `/jffs/rogui/overlay.tgz`。
5. 要回到蓝色界面：刷 KoolCenter 原版固件。刷坏了进不了系统：用华硕的救援模式（拔电，按住 reset 再插电）刷原版固件。

## 和原厂界面的差别

- 原厂的 VPN Fusion（含 Surfshark、NordVPN 一键登录）换成了 Merlin 的 VPN 页面：VPN Status、VPN Director、OpenVPN 和 WireGuard 的客户端与服务器。原厂那套页面要调用 KoolCenter 后端没有的接口。
- 6GHz AFC、天线灯、Instant Guard 站点互联：GT-BE98 Pro 的原厂 httpd 里也没有对应接口，不是 rogui 去掉的。
- 菜单逐项对照见 [MENU-COMPARE.md](MENU-COMPARE.md)。

## 顺手修掉的原厂 bug

原厂首页和 Game Dashboard 上的 2.4/5/6-1/6-2 频段图标，会把各个主网络的频段掩码**相加**（`mainFHNum += wifi_band`）。有两个主网络都带同一个频段位时就会进位。例如 5G+6G-1 的 MLO 网络是 58，单独的 6G-2 网络是 80，加起来是 138，6G-1 和 6G-2 两位被冲掉：两个 6G 射频都在发，图标却是灭的。rogui 把它改成了按位或（`|=`）。Asuswrt-Merlin 仓库里最新导入的华硕 ROG/TUF 界面源码还是 `+=`。

## 原理

```
开机 → rogui.sh start
  1. 算固件自带 /www 的指纹，和补丁包里记的比；不一致就跳过
  2. 复制 /www 到 /tmp/.rogui_www/www 当底板（KoolCenter 原版网页）
  3. 解开 overlay.tgz 盖上去（原厂 ROG 网页 + 补丁，约 13MB）
  4. mount --bind 到 /www（squashfs 只读，只能「盖住」），重启 httpd；网页起不来就自动撤回
每次服务事件后 → rogui.sh ensure
  有些设置（例如触发 restart_net 的）会让固件重写 rc_support，丢掉 rog，页面背景变白；这里补回
```

- 能行，是因为 KoolCenter 和原厂来自同一份华硕源码。原厂页面用到的 199 个 ASP 函数、77 个 cgi、37 个 action_mode，在 Merlin 3006.102 的 httpd/rc 里几乎都有。
- 补丁包在电脑上由 `rogui/build.py` 生成：
  - 只打包和 KoolCenter 不一样的文件；
  - 搬过来的 Merlin 页面要按字典重新映射 `<#N#>` 编号（两边字典行号不同）；
  - 把 Merlin 页面和软件中心补进菜单，软件中心的接入照搬 KoolCenter 给 GT-BE96 做的 ROG 官改；
  - 补上 Merlin 页面要用、原厂 js 里没有的函数，去掉指向不存在页面的菜单项。
- `update.sh` 用纯 Python 的 squashfs 读取器（`rogui/sqfs.py`）直接从固件文件里拆 `/www`，结果和从路由器上拉下来的逐字节相同。
- 仓库里不放打好的补丁包：包里是华硕原厂的网页文件，而且只对一版固件有效。脚本从你自己的固件文件现拆现拼。

## 已知现象（不用修）

- 有几个页面的标题写错了（AdGuard、VPN 服务器、流量统计、DNS Director、Security Notification）：原厂或 Merlin 的原文件就是这样。
- 网络地图反复进入时，Console 里有一条 MutationObserver 报错：原厂 `index.asp` 自带，页面功能正常。
- 登录后进的是网络地图，不是 Game Dashboard：KoolCenter 删了那个判断。

## 开发

- 改了 `build.py` 等代码之后跑 `python3 -I rogui/selftest.py`，标准是「失败 0」。它按 `rogui/golden.json` 重新拆固件、打包，比对每个文件的哈希。缺少的固件文件会跳过，不算失败。
- 每次打包后 `check.py` 会做静态检查：合并后才出现的断链、后端缺的函数、只有原厂页面请求的 `.cgi`、字典编号越界。
- 哪些页面用 KoolCenter 版、菜单补哪些项，在 `build.py` 顶部的 `PREFER_KC`、`MENU_*` 里改。
- 完整的验证标准和历史 bug 对照见 [rogui/TESTING.md](rogui/TESTING.md)。部署后的只读检查用 `bash rogui/status.sh`，ssh 目标用环境变量 `ROUTER` 指定。

## 说明

这不是 KoolCenter 官方出品。用了 rogui 之后界面上的问题，请在本仓库提 issue。

软件中心和梅林改版来自 [KoolCenter](https://www.koolcenter.com/)，Merlin 页面来自 [Asuswrt-Merlin](https://github.com/RMerl/asuswrt-merlin.ng)，ROG 网页来自华硕原厂固件。
