#!/bin/sh
# 只读检查 GT-BE98 Pro 上 rogui 和软件中心的状态
# 用法: bash status.sh    (可用环境变量 ROUTER 覆盖 ssh 目标)
ROUTER="${ROUTER:-admin@192.168.50.1}"

ssh "$ROUTER" /bin/sh <<'REMOTE'
echo "== 固件"
echo "  $(nvram get productid) $(nvram get firmver).$(nvram get buildno)_$(nvram get extendno)"
echo "  软件中心 $(cat /koolshare/.soft_ver 2>/dev/null)"

echo "== rogui"
if [ -x /jffs/rogui/rogui.sh ] || [ -f /jffs/rogui/rogui.sh ]; then
	sh /jffs/rogui/rogui.sh status | sed 's/^/  /'
else
	echo "  [X] /jffs/rogui 不存在，补丁包没部署"
fi
n=$(grep -c " /www " /proc/mounts)
[ "$n" -gt 1 ] && echo "  [X] /www 挂了 $n 层，应该只有 1 层"
if grep -q rogui.sh /jffs/scripts/services-start 2>/dev/null; then
	echo "  [OK] 开机自启已挂在 services-start"
else
	echo "  [X] services-start 里没有 rogui，重启后不会自动启用"
fi
if grep -q "rogui.sh ensure" /jffs/scripts/service-event-end 2>/dev/null; then
	echo "  [OK] service-event-end 里有 ensure 钩子"
else
	echo "  [X] service-event-end 里没有 ensure 钩子，固件重置 rc_support 后背景会变白；跑一次 rogui.sh install"
fi
if grep -q " /www " /proc/mounts; then
	case " $(nvram get rc_support) " in
		*" rog "*) echo "  [OK] rc_support 含 rog" ;;
		*) echo "  [X] 已挂载但 rc_support 缺 rog，页面背景会变白；跑 sh /jffs/rogui/rogui.sh ensure" ;;
	esac
fi
if [ -e /www/res/softcenter.css ]; then
	echo "  [OK] /www/res 链接正常"
else
	echo "  [X] /www/res 不通，软件中心会白屏"
fi
echo "  [信息] 最近的 rogui 日志:"
grep rogui /jffs/syslog.log 2>/dev/null | tail -3 | sed 's/^/    /'

echo "== 软件中心"
echo "  sc_url=$(nvram get sc_url)"
echo "  sc_skin=$(nvram get sc_skin)"
cmp -s /koolshare/res/softcenter.css /koolshare/res/softcenter_rog.css && echo "  [OK] softcenter.css 是 ROG 版" || echo "  [X] softcenter.css 不是 ROG 版"

echo "== jffs"
df -h /jffs | tail -1 | awk '{print "  已用 "$3" / "$2"，剩 "$4}'
REMOTE
