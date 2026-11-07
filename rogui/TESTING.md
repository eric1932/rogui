# rogui 的验证标准

改了 `rogui/` 下的代码、或者拿到新固件时，按这里验证。期望值都存在 `golden.json` 里，`selftest.py` 会自动核对。

## 什么时候做什么

| 场景 | 要做的 |
|---|---|
| 改了 build.py、check.py、fwextract.py 等代码 | 第 1 节自测，必须全部通过 |
| KoolCenter 出了新固件，或换了原厂固件版本 | 第 2 节 update.sh → 部署 → 第 3 节路由器上核对 → 第 4 节浏览器里看 |
| 界面上发现问题 | 先查 [README](../README.md#出问题怎么办) 里的已知现象，再看第 5 节该由哪道检查拦住 |

## 1. 自测（电脑上，约 1 分钟，不碰路由器）

```sh
python3 -I rogui/selftest.py
```

标准：**失败 0**。前两类检查遇到缺少的固件文件会显示「跳过」，不算失败；反例不跳过，要用到 KoolCenter 102.8_0、102.7_2 和原厂 102_39441，缺了会判失败。

它按 `golden.json` 核对三类东西：

- 每个固件文件拆出的 `/www`：指纹、文件数、链接数；
- 每组「KoolCenter + 原厂」打出的补丁包：内容哈希、文件数、配套的固件指纹、包名。其中 KoolCenter 102.8_0 + 原厂 102_39441 这一组还会跑静态检查，必须 0 项；
- 反例：把原厂当 KoolCenter、参数放反、把 KoolCenter 当原厂、文件不存在，都必须报错，而且不能产出补丁包。

`golden.json` 里记的是 KoolCenter 102.7_2、102.8_0 和原厂 102_39386、102_39441。固件文件放在仓库根目录，文件名和 `golden.json` 里的一致。

**有意改变输出时**（比如往菜单里加了一项），自测会报「内容哈希不同」。这时把新旧两个补丁包都解开，逐个文件比（补丁包是外层 tar 里套着 `rogui/overlay.tgz`，要用 `tar` 解两层），确认差异全是预期的，再把新值写进 `golden.json`，并在提交说明里写清楚为什么变。

指纹的算法见 `fwextract.fingerprint()`：按 C 语言顺序列出每个文件的 `md5  ./路径`，再列出链接，整体取 md5。路由器上的 `rogui.sh` 用的是同一个算法，两边必须逐字节一致，开机时的配套检查才有意义。补丁包的内容哈希，是对补丁包里 overlay 的文件用同样的方法算的。

## 2. 新固件：update.sh

```sh
rogui/update.sh <新的 KoolCenter 固件.pkgtb> [原厂固件.zip]
```

标准：

- 显示「✅ 通过」，包出现在 `rogui/dist/`；
- 静态检查显示「共 0 项需要人工判断」；
- 第 2b 项（同样缺函数、但不会报错的）出现下面这些名字属于正常：`channel_list_60g, generate_trans_id, get_all_groups, get_permissions_of_group, get_rbkList, lacp_wan, pms_devgroup_info, pms_device_info, set_group_all_folder_permission, set_group_permission, start_mac_clone, wan_bonding_*, wl_edmg_channel`。出现新名字时看一眼。

没通过时，包和同名的 `.check.txt` 报告放在 `rogui/dist/failed/`，不要部署。

## 3. 路由器上核对（部署后）

除了最后一项，都是只读检查。最后一项会改 nvram、重启一个服务，用来验证补回钩子。

```sh
ROUTER=admin@192.168.50.1 bash rogui/status.sh
```

标准：

- 挂载版显示 `挂载: 已启用`，`/www` 上只有 1 层挂载；固件版显示 `挂载: 不需要（固件自带 ROG 网页）`，`/www` 上没有挂载。两种都要有 `[OK] /www/res 链接正常`，开机自启在 services-start 里。
- `rc_support: 含 rog`；`/jffs/scripts/service-event-end` 里有 `rogui.sh ensure`。
- `sc_skin=ROG`，`softcenter.css` 是 ROG 版。
- 挂载版：`/tmp/.rogui_fp` 等于补丁包的 `built_for`，也等于 `golden.json` 里对应 KoolCenter 固件的指纹。
- 合成后的 `/www` 指纹，等于自测最后打印的值（`golden.json` 的 `router.merged_www_fp`，对应 KoolCenter 102.8_0 + 原厂 102_39441）。固件版的 `rogui.sh status` 会直接显示它；挂载版在路由器上这样算，和 `rogui.sh` 里的 `www_fp()` 相同：
  ```sh
  cd /www && { find . -type f | LC_ALL=C sort | while IFS= read -r f; do md5sum "$f"; done; find . -type l | LC_ALL=C sort | while IFS= read -r l; do echo "$l -> $(readlink "$l")"; done; } | md5sum
  ```
- 重启一次后，以上仍然成立。
- 模拟固件重置 `rc_support`，再触发一个无害的服务事件，`rog` 应该自动补回，syslog 里有一条「已补回」。`restart_time` 会顺带重启 sshd，所以第一个 ssh 显示 `closed by remote host` 是正常的，检查放在第二个 ssh 里：
  ```sh
  ssh admin@192.168.50.1 'nvram set rc_support="$(nvram get rc_support | sed "s/ rog\$//; s/ rog / /")"; service restart_time'; sleep 5; ssh admin@192.168.50.1 'sh /jffs/rogui/rogui.sh status | grep rc_support; grep rogui /jffs/syslog.log | tail -1'
  ```

## 4. 浏览器里看

先强制刷新，再退出重新登录，原因见 README「安装」第 3 步。然后把每个菜单和顶部的标签页都点开一遍，标准是：没有 404，Console 里没有新的红色报错，页面上没有露出 `<#数字#>`。

重点看这几处：

- 登录页、Game Dashboard、网络地图：风险最高的原厂页面。
- System Info、系统管理 → Tweaks：Merlin 页面，看文字有没有错乱，这是在验证字典编号的映射。
- 电竞加速 → Classification、网络工具 → Site Survey：依赖 build.py 补进去的函数。
- 电竞加速和 QoS 页面：原厂页面认不出 Merlin 的 Cake，看显示是否正常。
- VPN Director、OpenVPN 客户端：Merlin 版页面能打开。
- 软件中心：在菜单最后一项，ROG 样式，插件列表能加载。
- 无线 → 常规：保存一次，确认能保存、Wi-Fi 正常。
- 系统管理 → 固件升级、恢复/导出设置：只看不点。

## 5. 每道检查防的是什么

下面每一行都是出过的问题。改代码时别把对应的检查去掉。

| 问题 | 不拦会怎样 | 由谁拦住 |
|---|---|---|
| 原厂 `ajax_coretmp.asp` 调用 Merlin 没有的函数 | System Info 温度面板空白、JS 语法错误 | check.py 第 2a 项；`PREFER_KC` |
| 菜单项指向固件里不存在的页面（GRE 等） | 点开 404 | build.py 去掉悬空菜单项；check.py 第 1 项 |
| 原厂 `VPN/` 视图调用 KoolCenter 没有的 surfshark 接口 | 用到时失败 | check.py 第 3 项；`PREFER_KC_DIRS` |
| 字典编号错位 | 菜单标签全错 | 自测的内容哈希；DictRemap 只映射 KoolCenter 来源的行 |
| 插件安装脚本执行 `rm -rf /tmp/<插件名>*`，删掉了工作目录 | 网页全部 404 | 工作目录改成以点开头的 `/tmp/.rogui_www`；status 发现 `/www` 为空会警告 |
| 检查没过的包留在 `dist/` 被误部署 | — | update.sh 先拼到临时目录，通过了才放进 `dist/` |
| 把 Merlin 或 KoolCenter 当原厂输入 | 拼出错的包 | build.py 核对输入；自测的反例 |
| 先部署了新包、还没刷对应固件 | 正在用的 ROG 界面被撤掉 | rogui.sh 挂载时记下指纹，不配套时保持现状 |
| 网页上应用设置触发 `restart_net`，固件重写 `rc_support`，丢掉 `rog` | 所有页面背景变白，横幅变成带「退出/重新启动」按钮的华硕版 | `service-event-end` 钩子调用 `rogui.sh ensure` 补回；status 会警告 |
| 原厂首页和 Game Dashboard 把各主网络（MAINFH）的频段掩码相加（`mainFHNum += wifi_band`），两个主网络带同一位时进位 | 射频在发，频段图标却是灭的 | build.py 的 `patch_band_or` 改成按位或；原厂改了写法时，build 报告里会出「警告」 |
