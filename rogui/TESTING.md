# rogui 验证的黄金标准

改了 `rogui/` 下的代码、或者拿到新固件时，按这里的标准验证。数值都存在 `golden.json`，`selftest.py` 会自动核对。

## 什么时候做什么

| 场景 | 要做的 |
|---|---|
| 改了 build.py / check.py / fwextract.py 等代码 | 跑第 1 节自测，必须全部通过 |
| KoolCenter 出了新固件 | 第 2 节 update.sh → 部署后第 3 节路由器核对 → 第 4 节界面 |
| 换了原厂固件版本 | 同上 |
| 界面上发现问题 | 先查第 5 节"已知可接受"，再查第 6 节"历史 bug 对照" |

## 1. 自测（Mac 上，约 1 分钟，不碰路由器）
```sh
python3 -I rogui/selftest.py
```
标准：**失败 0**。缺少的固件文件会显示"跳过"，不算失败。

检查内容和当前黄金值（2026-10-20）：

| 项 | 输入 | 黄金值 |
|---|---|---|
| 固件 /www 指纹 | KoolCenter 102.8_0 | `45f16f79…`（1195 个文件，32 个链接） |
| | KoolCenter 102.7_2 | `2e1532a7…` |
| | 原厂 39441 | `9bad0bfb…`（1353 / 10） |
| | 原厂 39386 | `97ad8f38…`（1352 / 10） |
| 补丁包内容 | 102.8_0 + 原厂 39441（**正在用的**） | 645 个文件，内容哈希 `e5e99977…`，静态检查 0 项 |
| | 102.7_2 + 原厂 39441 | 657 个文件，`23b0ae8d…` |
| | 102.8_0 + 原厂 39386 | 642 个文件，`0de7a4ea…` |
| 反例：必须报错且不产出包 | 原厂当 KoolCenter、参数放反、KoolCenter 当原厂、文件不存在 | 报错文字见 golden.json |

**有意改变输出时**（比如往菜单里加了一项）：自测会报"内容哈希不同"。这时要人工核对差异：用 `fwextract.py` 拆出新旧两个包逐个文件比，确认差异全是预期的，再把新值写进 `golden.json`，并在提交说明里写清楚为什么变。

指纹和内容哈希的算法见 `fwextract.fingerprint()`：按 C 语言顺序列出每个文件的 `md5  ./路径`，再列出链接，整体取 md5。内容哈希是对补丁包里 overlay 的文件用同样的方法算。

## 2. 新固件：update.sh
```sh
rogui/update.sh <新的 KoolCenter 固件.pkgtb> [原厂固件.zip]
```
标准：
- 最后一行是"✅ 通过"，包出现在 `rogui/dist/`
- 静态检查"共 0 项需要人工判断"
- 第 2b 项（不会报错的缺函数）出现以下函数属于正常：`channel_list_60g, generate_trans_id, get_all_groups, get_permissions_of_group, get_rbkList, lacp_wan, pms_devgroup_info, pms_device_info, set_group_all_folder_permission, set_group_permission, start_mac_clone, wan_bonding_*, wl_edmg_channel`。出现新名字时看一眼

没通过时，包会放在 `rogui/dist/failed/`，报告是同名的 `.check.txt`。这时不要部署，交给人或 AI 判断。

## 3. 路由器上核对（部署后，只读）
```sh
bash rogui/status.sh
```
标准：
- `挂载: 已启用`；`/www` 只有 1 层挂载；`[OK] /www/res 链接正常`；开机自启在 services-start 里
- `rc_support: 含 rog`；`/jffs/scripts/service-event-end` 里有 `rogui.sh ensure`
- `/tmp/.rogui_fp` 等于补丁包的 `built_for`，也等于第 1 节里对应 KoolCenter 固件的指纹
- 102.8_0 + 原厂 39441 时，挂载状态下用 rogui.sh 的 `www_fp()` 算出的合成后指纹是 `95c68d63bd22024cd1ae5fc86c29a010`（2026-10-20 频段图标修复前是 `21fef585…`）
- `sc_skin=ROG`，`softcenter.css` 是 ROG 版
- 重启一次后以上仍然成立（开机自启）
- 模拟固件重置 rc_support，再触发一个无害的服务事件，`rog` 应自动补回，syslog 里有一条"已补回"。`restart_time` 会顺带重启 sshd，所以第一个 ssh 会显示 `closed by remote host`，属于正常；检查放在第二个 ssh 里（2026-10-15 实测补回只用了约 1 秒）：
  ```sh
  ssh admin@192.168.50.1 'nvram set rc_support="$(nvram get rc_support | sed "s/ rog\$//; s/ rog / /")"; service restart_time'; sleep 5; ssh admin@192.168.50.1 'sh /jffs/rogui/rogui.sh status | grep rc_support; grep rogui /jffs/syslog.log | tail -1'
  ```

## 4. 界面
- 浏览器 **Cmd+Shift+R** 强制刷新（CSS 缓存 1 小时，不强刷会看到旧图标）
- 自动巡检：`BROWSER-CRAWL-PROMPT.md`，交给浏览器 agent，标准是没有 404、没有新的 JS 报错
- 肉眼巡检：`BROWSER-TEST-PROMPT.md` 和 `TEST-PLAN.md`

## 5. 已知、可接受的现象（不用修）
- 5 个页面标题写错（AdGuard、VPN 服务器、流量统计、DNS Director、Security Notification）：原厂或 Merlin 原文件就这样
- 网络地图反复进入时 Console 有一条 MutationObserver 报错：原厂 index.asp 自带，页面功能正常
- 退出登录页的青色问号框：原厂设计图 `icon_Sec_hint.png`
- 登录后进的是网络地图，不是 Game Dashboard：KoolCenter 删了那个判断

## 6. 历史 bug 和防线对照
| bug | 现象 | 现在由谁拦住 |
|---|---|---|
| 原厂 `ajax_coretmp.asp` 调用 Merlin 没有的函数 | System Info 温度面板空白、JS 语法错误 | check.py 第 2a 项；`PREFER_KC` |
| 菜单项指向固件里不存在的页面（GRE 等） | 点开 404 | build.py 去掉悬空菜单项；check.py 第 1 项 |
| 原厂 `VPN/` 视图调用 KoolCenter 没有的 surfshark 接口 | 用到时失败 | check.py 第 3 项；`PREFER_KC_DIRS` |
| 字典编号错位 | 菜单标签全错 | 自测内容哈希；DictRemap 只映射 KoolCenter 来源的行 |
| 插件安装脚本 `rm -rf /tmp/<插件名>*` 删掉工作目录 | 网页全部 404 | 工作目录改为 `/tmp/.rogui_www`；status 发现 /www 为空会警告 |
| 检查没过的包留在 dist/ 被误部署 | — | update.sh 先拼到临时目录，通过才放进 dist/ |
| 把 Merlin 或 KoolCenter 当原厂输入 | 拼出错的包 | build.py 输入核对；自测第 3 节 |
| 先部署新包、还没刷固件 | 正在用的 ROG 界面被撤掉 | rogui.sh 挂载时记下指纹，不配套时保持现状 |
| 浏览器缓存 | 新加的菜单没图标 | 第 4 节强制刷新 |
| 网页上应用设置触发 restart_net，固件重写 rc_support 丢掉 `rog` | 所有页面背景变白，横幅变成带"退出/重新启动"按钮的华硕版 | `service-event-end` 钩子调用 `rogui.sh ensure` 补回；status 会警告 |
| 原厂首页、电竞仪表板把各主网络（MAINFH）的频段掩码相加（`mainFHNum += wifi_band`），两个主网络带同一位时进位 | 射频在发，频段图标却灭（例：5G+6G-1 的 MLO 网络 58 + 6G-2 网络 80 = 138，两个 6G 都灭） | build.py `patch_band_or` 改成按位或；原厂改了写法时 build 报告里会出"警告" |
