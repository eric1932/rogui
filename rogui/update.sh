#!/bin/bash
# 一键生成 rogui 补丁包：直接从固件文件里拆 /www，拼补丁，再做静态检查。不碰路由器。
#
# 用法:
#   ./update.sh <KoolCenter 固件.pkgtb> [原厂固件.zip 或 .pkgtb]
#   ROUTER=admin@192.168.50.1 ./update.sh ...   # 指定打印出的部署命令里的 ssh 目标
#
# 原厂固件不写时，默认用项目目录里文件名排序最新的 FW_GT-BE98_Pro_*.zip。
# 检查全部通过才算成功；有问题会停下并保留报告，交给人或 AI 判断。
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
DIST="${SCRIPT_DIR}/dist"
# 打印部署命令时用的 ssh 目标，可用环境变量覆盖，例如 ROUTER=admin@192.168.50.1
ROUTER="${ROUTER:-admin@192.168.50.1}"

KC="$1"
STOCK="$2"
if [ -z "${KC}" ]; then
	sed -n '2,9p' "$0"
	exit 1
fi
if [ -z "${STOCK}" ]; then
	STOCK="$(ls "${PROJECT_DIR}"/FW_GT-BE98_Pro_*.zip 2>/dev/null | sort | tail -1)"
	[ -n "${STOCK}" ] || { echo "没找到原厂固件，请作为第二个参数传入"; exit 1; }
fi
for f in "${KC}" "${STOCK}"; do
	[ -f "${f}" ] || { echo "文件不存在: ${f}"; exit 1; }
done

echo "== KoolCenter: $(basename "${KC}")"
echo "== 原厂:       $(basename "${STOCK}")"
echo
# 先拼到临时目录，检查通过才挪进 dist/，避免覆盖已经验证过的同名补丁包
mkdir -p "${DIST}"
TMP="$(mktemp -d "${DIST}/.build.XXXXXX")"
trap 'rm -rf "${TMP}"' EXIT

echo "== 1/2 拼补丁包"
OUT=$(python3 -I "${SCRIPT_DIR}/build.py" --stock "${STOCK}" --kc "${KC}" --out "${TMP}")
echo "${OUT}" | sed 's/^/   /'
PKG_TMP=$(echo "${OUT}" | sed -n 's/^输出: //p')
[ -f "${PKG_TMP}" ] || { echo "没找到输出的补丁包"; exit 1; }
NAME="$(basename "${PKG_TMP}" .tgz)"

echo
echo "== 2/2 静态检查"
REPORT_TMP="${TMP}/${NAME}.check.txt"
RC=0
python3 -I "${SCRIPT_DIR}/check.py" --stock "${STOCK}" --kc "${KC}" --pkg "${PKG_TMP}" > "${REPORT_TMP}" || RC=$?
sed 's/^/   /' "${REPORT_TMP}"
echo
if [ "${RC}" -eq 0 ]; then
	mv -f "${PKG_TMP}" "${REPORT_TMP}" "${DIST}/"
	PKG="${DIST}/${NAME}.tgz"
	echo "✅ 通过。补丁包: ${PKG}"
	echo "刷好这版 KoolCenter 固件后，部署命令:"
	echo "  cat \"${PKG}\" | ssh ${ROUTER} 'tar xzf - -C /jffs && sh /jffs/rogui/rogui.sh install'"
elif [ "${RC}" -eq 1 ] && tail -1 "${REPORT_TMP}" | grep -q '^共 [0-9]* 项需要人工判断$'; then
	mkdir -p "${DIST}/failed"
	mv -f "${PKG_TMP}" "${REPORT_TMP}" "${DIST}/failed/"
	echo "⚠️  检查发现需要人工判断的问题，补丁包先别部署。补丁包和报告在: ${DIST}/failed/${NAME}.*"
	exit 2
else
	echo "❌ check.py 运行出错（退出码 ${RC}），没有产出补丁包"
	exit 1
fi
