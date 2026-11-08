#!/bin/sh
# rogui.sh — 在 KoolCenter 梅林改版上叠加原厂 ROG 网页
#
#   rogui.sh install  挂好开机自启和服务事件钩子（可重复执行），然后 start
#   rogui.sh uninstall 去掉开机自启和钩子，然后 stop
#   rogui.sh start    把 KoolCenter 的 /www 复制到内存，盖上 overlay.tgz，删掉 remove.txt 里列的文件，
#                     再 bind mount 到 /www
#   rogui.sh stop     撤掉挂载，回到 KoolCenter 原界面
#   rogui.sh ensure   挂载状态下补回被固件重置的 rc_support rog（service-event-end 自动调用）
#   rogui.sh status   看当前状态
#
# 用 bake.sh 做出来的固件本身就带着 ROG 网页（"固件内置"）：start 不挂载，只补 rc_support 里的 rog；
# ensure 照常补回；stop 撤不掉，要回到蓝色界面得刷 KoolCenter 原版固件。这时 overlay.tgz 用不上，可以删。
#
# 安全开关:
#   touch <本目录>/disable      之后 start 一律跳过（开机也不生效）
#   固件自带 /www 的指纹和 built_for 对不上时 start 也会跳过（升级固件后要重新 build）
#   start 后网页起不来会自动 stop

DIR=$(cd "$(dirname "$0")" && pwd)
# 工作目录必须避开软件中心插件安装脚本的清理通配符：rog 工具箱插件安装时会执行
# rm -rf /tmp/${module}*（即 /tmp/rog*），以前叫 /tmp/rogui 会被一起删掉。
# 以点开头的名字不会被 /tmp/xxx* 这类通配符匹配到。
WORK=/tmp/.rogui_www
SKIN_SAVE=/tmp/.rogui_sc_skin
# 固件自带 /www 的指纹，挂载成功时记下。/tmp 重启才清空，而固件不重启换不了，所以挂载期间一直有效
FP_CACHE=/tmp/.rogui_fp
TAG=rogui

log() { echo "[$TAG] $*"; logger -t "$TAG" "$*" 2>/dev/null; }

mounted() { grep -q " /www " /proc/mounts; }

# 固件内置 ROG 网页：/www 没有挂载，配色却已经是 ROG 红。判断方法和软件中心 kscore.sh 的 set_skin 一样，
# KoolCenter 原版固件的 /www 不会是这个颜色。
baked() {
	! mounted && grep -A1 ".tab_NW:hover{" /www/form_style.css 2>/dev/null | grep background | sed 's/,//g' | grep -q 2071044
}

# 固件自带 /www 的指纹。算法必须和 fwextract.py 的 fingerprint() 逐字节一致。
# 只有在 /www 没被挂载时才代表固件原版。
www_fp() {
	( cd /www && {
		find . -type f | LC_ALL=C sort | while IFS= read -r f; do md5sum "$f"; done
		find . -type l | LC_ALL=C sort | while IFS= read -r l; do echo "$l -> $(readlink "$l")"; done
	} | md5sum | cut -d' ' -f1 )
}

http_ok() {
	if [ "$(nvram get http_enable)" = "1" ]; then
		url="https://127.0.0.1:$(nvram get https_lanport)/Main_Login.asp"
	else
		url="http://127.0.0.1:$(nvram get http_lanport)/Main_Login.asp"
	fi
	i=0
	while [ $i -lt 15 ]; do
		code=$(curl -k -s -o /dev/null -w '%{http_code}' -m 5 "$url" 2>/dev/null)
		[ "$code" = "200" ] && return 0
		i=$((i + 1))
		sleep 2
	done
	log "网页检查失败: $url 返回 ${code:-无响应}"
	return 1
}

add_rog_support() {
	rs=$(nvram get rc_support)
	case " $rs " in
		*" rog "*) ;;
		*) nvram set rc_support="$rs rog" ;;
	esac
}

del_rog_support() {
	rs=$(nvram get rc_support)
	nvram set rc_support="$(echo " $rs " | sed 's/ rog / /g; s/^ //; s/ $//')"
}

do_stop() {
	if baked; then
		log "ROG 网页是固件自带的，stop 撤不掉；要回到蓝色界面，请刷 KoolCenter 原版固件"
		return 1
	fi
	if mounted; then
		# httpd 的工作目录还在旧的 /www 里，普通 umount 会报 busy；懒卸载随后重启 httpd 即可释放
		# 可能叠了不止一层（并发 start 等），全部卸掉；卸不动就停，免得死循环
		while mounted; do
			umount /www 2>/dev/null || umount -l /www || break
		done
		del_rog_support
		if [ -e $SKIN_SAVE ]; then
			skin=$(cat $SKIN_SAVE)
			skin=${skin:-ASUSWRT}
			nvram set sc_skin="$skin"
			case "$skin" in
				ASUSWRT) css=asus ;;
				*) css=$(echo "$skin" | tr 'A-Z' 'a-z') ;;
			esac
			[ -f "/koolshare/res/softcenter_${css}.css" ] && cp -f "/koolshare/res/softcenter_${css}.css" /koolshare/res/softcenter.css
			rm -f $SKIN_SAVE
		fi
		service restart_httpd >/dev/null 2>&1
		log "已撤掉挂载，回到 KoolCenter 原界面"
	else
		log "当前没有挂载"
	fi
	rm -rf "$WORK"
}

do_start() {
	if [ -e "$DIR/disable" ]; then
		log "发现 $DIR/disable，跳过"
		return 0
	fi
	# 固件内置：网页已经是 ROG 的，不用挂载，也不用设 sc_skin（软件中心开机时按 /www 的配色自己会设成 ROG）
	if baked; then
		add_rog_support
		log "固件自带 ROG 网页，不用挂载；已补上 rc_support 里的 rog"
		return 0
	fi
	if [ ! -f "$DIR/overlay.tgz" ]; then
		log "没有 $DIR/overlay.tgz，跳过（用自带 ROG 网页的固件时可以删掉它；刷回原版固件后要重新部署补丁包）"
		return 1
	fi
	# 已挂载时用挂载那一刻记下的指纹先比对：不配套就保持现状，不要先把正在用的界面撤掉
	fp=
	mounted && fp=$(cat $FP_CACHE 2>/dev/null)
	if [ -n "$fp" ] && [ "$fp" != "$(cat "$DIR/built_for" 2>/dev/null)" ]; then
		log "新补丁包和当前固件不配套（当前指纹 ${fp}），保持现状；刷好对应固件重启后会自动生效"
		return 1
	fi
	mounted && do_stop
	if mounted; then
		log "/www 还有挂载卸不掉，算不了固件原版指纹，跳过"
		return 1
	fi
	fp=$(www_fp)
	if [ "$fp" != "$(cat "$DIR/built_for" 2>/dev/null)" ]; then
		log "固件自带的网页和补丁包不配套（当前指纹 ${fp}，补丁包是给 $(cat "$DIR/built_for" 2>/dev/null) 做的），跳过；请用新固件重新 build"
		return 1
	fi

	rm -rf "$WORK"
	mkdir -p "$WORK/www" || return 1
	cp -a /www/. "$WORK/www/" || { log "复制 /www 失败"; rm -rf "$WORK"; return 1; }
	tar xzf "$DIR/overlay.tgz" -C "$WORK/www" || { log "解压 overlay.tgz 失败"; rm -rf "$WORK"; return 1; }
	# 精简（build.py --slim）：补丁包的 remove.txt 里列的文件不要，一行一个，相对 /www
	if [ -s "$DIR/remove.txt" ]; then
		while IFS= read -r p; do
			case "$p" in ''|/*|*..*) continue ;; esac
			rm -f "$WORK/www/$p"
		done < "$DIR/remove.txt"
	fi

	mount -o bind "$WORK/www" /www || { log "bind mount 失败"; rm -rf "$WORK"; return 1; }
	echo "$fp" > $FP_CACHE
	add_rog_support
	# 软件中心皮肤：原值记下来，stop 时还原
	[ -e $SKIN_SAVE ] || nvram get sc_skin > $SKIN_SAVE
	nvram set sc_skin=ROG
	[ -f /koolshare/res/softcenter_rog.css ] && cp -f /koolshare/res/softcenter_rog.css /koolshare/res/softcenter.css
	service restart_httpd >/dev/null 2>&1
	sleep 3

	if http_ok; then
		log "已启用 ROG 网页（浏览器里退出重新登录一次，菜单缓存才会刷新）"
	else
		log "网页起不来，自动回退"
		do_stop
		return 1
	fi
}

# 固件的一些服务事件会重跑 init_nvram，把 rc_support 整个重写，rog 就没了（2026-10-15：网页上应用
# 一次触发 restart_net 的设置后丢失）。页面随即走非 ROG 分支：body 不加 bg 类所以背景全白，
# 横幅换成带"退出/重新启动"按钮的华硕版。service-event-end 在每次服务事件后调这里补回。
# 只改 nvram，不重启 httpd（页面每次打开都现读 rc_support）。
do_ensure() {
	mounted || baked || return 0
	[ -e "$DIR/disable" ] && return 0
	case " $(nvram get rc_support) " in
		*" rog "*) return 0 ;;
	esac
	add_rog_support
	log "rc_support 里的 rog 被固件重置（服务事件: $*），已补回"
}

HOOK=/jffs/scripts/services-start
EVENT_HOOK=/jffs/scripts/service-event-end

# $1 文件 $2 要加的行 $3 识别已加过的关键字
add_hook() {
	[ -f "$1" ] || printf '#!/bin/sh\n' > "$1"
	if ! grep -q "$3" "$1"; then
		echo "$2" >> "$1"
		log "已加入 $1"
	fi
	chmod +x "$1"
}

do_install() {
	[ "$(nvram get jffs2_scripts)" = "1" ] || log "警告: jffs2_scripts 不是 1，/jffs/scripts 不会被执行，开机自启无效"
	add_hook "$HOOK" "(sleep 5; sh $DIR/rogui.sh start) >/dev/null 2>&1 &" "rogui.sh start"
	add_hook "$EVENT_HOOK" "sh $DIR/rogui.sh ensure \"\$@\" >/dev/null 2>&1" "rogui.sh ensure"
	do_start
}

do_uninstall() {
	[ -f "$HOOK" ] && sed -i '/rogui.sh start/d' "$HOOK"
	[ -f "$EVENT_HOOK" ] && sed -i '/rogui.sh ensure/d' "$EVENT_HOOK"
	log "已去掉开机自启和服务事件钩子"
	do_stop
}

do_status() {
	if mounted; then
		echo "挂载: 已启用"
		[ -e /www/state.js ] || echo "警告: /www 是空的（工作目录被删了），请重新执行 start"
	elif baked; then
		echo "挂载: 不需要（固件自带 ROG 网页）"
	else
		echo "挂载: 未启用"
	fi
	[ -e "$DIR/disable" ] && echo "disable 开关: 打开（start 会跳过）"
	echo "当前固件: $(nvram get buildno)_$(nvram get extendno)"
	if baked; then
		echo "固件自带 /www 的指纹: $(www_fp)"
	else
		echo "补丁包对应的 /www 指纹: $(cat "$DIR/built_for" 2>/dev/null)"
		[ -s "$DIR/remove.txt" ] && echo "精简: 合成时删掉 $(wc -l < "$DIR/remove.txt" | tr -d ' ') 个文件"
		mounted || echo "当前 /www 指纹: $(www_fp)"
	fi
	case " $(nvram get rc_support) " in
		*" rog "*) echo "rc_support: 含 rog" ;;
		*) echo "rc_support: 不含 rog"
		   { mounted || baked; } && echo "警告: ROG 网页在用但缺 rog，页面背景会变白；跑 ensure 补回，并检查 $EVENT_HOOK 里的钩子" ;;
	esac
	grep -q "rogui.sh ensure" "$EVENT_HOOK" 2>/dev/null || echo "警告: $EVENT_HOOK 里没有 ensure 钩子，跑一次 install"
	echo "sc_skin: $(nvram get sc_skin)"
}

case "$1" in
	install) do_install ;;
	uninstall) do_uninstall ;;
	start) do_start ;;
	stop) do_stop ;;
	ensure) shift; do_ensure "$@" ;;
	status) do_status ;;
	*) echo "用法: $0 install|uninstall|start|stop|ensure|status"; exit 1 ;;
esac
