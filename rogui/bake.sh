#!/bin/bash
# 把 rogui 补丁包直接做进 KoolCenter 固件，产出一个自带 ROG 网页的 .pkgtb。不碰路由器。
#
# 只能在 Linux 上用 root 跑：解包和重新打包时要原样保留属主和设备文件，macOS 做不到。
# 需要 squashfs-tools 和 python3。macOS 上用 bake-docker.sh，GitHub 上用 .github/workflows/bake.yml。
#
# 用法:
#   sudo rogui/bake.sh <KoolCenter 固件.pkgtb> <rogui 补丁包.tgz> [输出目录，默认 rogui/dist]
#
# 做法：拆出根文件系统，原样解开；把 overlay 解到 /www 上（和 rogui.sh start 的合成方式一样）；
# 用和原包相同的参数重新打包；只改 FIT 头里根文件系统的大小和 sha256。最后把产物重新拆开，
# 和原包逐项对比（fwbake.py verify），全部通过才保留产物。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

die() { echo "❌ $*" >&2; exit 1; }

KC="${1:-}"
PKG="${2:-}"
OUTDIR="${3:-${SCRIPT_DIR}/dist}"
[ -n "${KC}" ] && [ -n "${PKG}" ] || { sed -n '2,13p' "$0"; exit 1; }
[ -f "${KC}" ] || die "文件不存在: ${KC}"
[ -f "${PKG}" ] || die "文件不存在: ${PKG}"
[ "$(uname -s)" = Linux ] || die "只能在 Linux 上跑；macOS 用 rogui/bake-docker.sh"
[ "$(id -u)" = 0 ] || die "要用 root 跑（sudo），否则解包时属主和设备文件会丢"
for t in unsquashfs mksquashfs python3; do
	command -v "$t" >/dev/null || die "缺少 $t（apt-get install squashfs-tools python3）"
done

W="$(mktemp -d)"
trap 'rm -rf "${W}"' EXIT
NAME="$(basename "${KC}" .pkgtb)-$(basename "${PKG}" .tgz | sed 's/^rogui-[^-]*-/rogui-/')"
mkdir -p "${OUTDIR}"
OUT="${OUTDIR}/${NAME}.pkgtb"
REPORT="${OUTDIR}/${NAME}.verify.txt"

echo "== KoolCenter 固件: $(basename "${KC}")"
echo "== rogui 补丁包:    $(basename "${PKG}")"

echo "== 1/5 拆出根文件系统"
python3 -I "${SCRIPT_DIR}/fwbake.py" split "${KC}" "${W}/orig" > "${W}/orig.json"
read -r COMP BS MKFS OPTS XATTR EXPORT < <(python3 -I -c '
import json, sys
q = json.load(open(sys.argv[1]))["sqfs"]
print(q["comp"], q["block_size"], q["mkfs_time"], q["comp_opts"] or "-", int(q["has_xattrs"]), int("EXPORTABLE" in q["flags"]))' "${W}/orig.json")
echo "   squashfs: ${COMP}，块 ${BS}，压缩选项 ${OPTS}，xattr ${XATTR}，可导出 ${EXPORT}"
[ "${OPTS}" = "-" ] || die "原包带了自定义压缩选项（${OPTS}），脚本还不会照抄"

echo "== 2/5 原样解开"
unsquashfs -no-progress -d "${W}/A" "${W}/orig/rootfs.sqfs" > /dev/null
[ -f "${W}/A/www/state.js" ] || die "根文件系统里没有 /www/state.js，不像华硕固件"

echo "== 3/5 合成 /www（原版 + overlay）"
mkdir -p "${W}/pkg"
tar -xzf "${PKG}" -C "${W}/pkg" rogui/overlay.tgz rogui/built_for
FP="$(python3 -I "${SCRIPT_DIR}/fwbake.py" fp "${W}/A/www")"
[ "${FP}" = "$(cat "${W}/pkg/rogui/built_for")" ] || die "补丁包是给 /www 指纹 $(cat "${W}/pkg/rogui/built_for") 的固件做的，这个固件是 ${FP}，先用 update.sh 为这版固件重新打补丁包"
cp -a "${W}/A" "${W}/C"
tar -xzf "${W}/pkg/rogui/overlay.tgz" -C "${W}/C/www"
# 解压时新建或改动过的目录，修改时间会变成"现在"。统一改成原包的打包时间，同样的输入就总能打出
# 逐字节相同的固件（本地和 GitHub 上打的可以互相核对）。文件的时间来自补丁包，本来就固定。
find "${W}/C/www" -type d -newermt "@${MKFS}" -exec touch -h -d "@${MKFS}" {} +

echo "== 4/5 按原参数重新打包，写回固件"
# 不加 -no-xattrs：原包没有 xattr 但也没设 NO_XATTRS 标记；解开的目录里没有 xattr 时，打出来的包和原包一样。
# 万一目录里混进了 xattr，verify 会因为 has_xattrs 不同而报错。
ARGS=(-comp "${COMP}" -b "${BS}" -noappend -no-progress -quiet -mkfs-time "${MKFS}")
[ "${EXPORT}" = 1 ] || ARGS+=(-no-exports)
mksquashfs "${W}/C" "${W}/new.sqfs" "${ARGS[@]}"
python3 -I "${SCRIPT_DIR}/fwbake.py" pack "${KC}" "${W}/new.sqfs" "${W}/out.pkgtb" | sed 's/^/   /'

echo "== 5/5 把产物重新拆开，逐项对比"
python3 -I "${SCRIPT_DIR}/fwbake.py" split "${W}/out.pkgtb" "${W}/back" > /dev/null
unsquashfs -no-progress -d "${W}/B" "${W}/back/rootfs.sqfs" > /dev/null
RC=0
python3 -I "${SCRIPT_DIR}/fwbake.py" verify "${KC}" "${W}/out.pkgtb" "${W}/A" "${W}/B" "${PKG}" > "${W}/report.txt" || RC=$?
sed 's/^/   /' "${W}/report.txt"
if [ "${RC}" -ne 0 ]; then
	mkdir -p "${OUTDIR}/failed"
	cp "${W}/report.txt" "${OUTDIR}/failed/${NAME}.verify.txt"
	die "对比没通过，没有产出固件。报告: ${OUTDIR}/failed/${NAME}.verify.txt"
fi
mv -f "${W}/out.pkgtb" "${OUT}"
cp "${W}/report.txt" "${REPORT}"
( cd "${OUTDIR}" && sha256sum "${NAME}.pkgtb" > "${NAME}.pkgtb.sha256" )
[ -n "${SUDO_UID:-}" ] && chown "${SUDO_UID}:${SUDO_GID:-${SUDO_UID}}" "${OUT}" "${REPORT}" "${OUT}.sha256"
echo
echo "✅ 产出: ${OUT}"
echo "   报告: ${REPORT}"
