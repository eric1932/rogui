#!/bin/bash
# 在 macOS 上用 Docker 跑 bake.sh（容器里是 Ubuntu 24.04，和 GitHub Actions 一样）。
# 两个输入文件都要放在项目目录里（容器只挂载项目目录）。产物放在 rogui/dist/。
#
# 用法:
#   rogui/bake-docker.sh <KoolCenter 固件.pkgtb> <rogui 补丁包.tgz>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
[ $# -eq 2 ] || { sed -n '2,6p' "$0"; exit 1; }

rel() {
	local p
	p="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
	case "${p}" in
		"${PROJECT_DIR}"/*) echo "${p#"${PROJECT_DIR}"/}" ;;
		*) echo "❌ $1 不在项目目录 ${PROJECT_DIR} 里" >&2; exit 1 ;;
	esac
}
KC="$(rel "$1")"
PKG="$(rel "$2")"

docker run --rm -v "${PROJECT_DIR}:/w" -w /w -e SUDO_UID="$(id -u)" -e SUDO_GID="$(id -g)" ubuntu:24.04 bash -c '
	set -e
	apt-get update -qq >/dev/null
	DEBIAN_FRONTEND=noninteractive apt-get install -y -qq squashfs-tools python3 >/dev/null
	bash rogui/bake.sh "$1" "$2" rogui/dist' _ "${KC}" "${PKG}"
