#!/bin/bash
# 用 GitHub Actions 把 rogui 做进固件（.github/workflows/bake.yml）。需要 gh 并已登录。
#
# 固件文件不能进公开仓库，也不能放进公开的 Actions artifact（那等于重新分发华硕和 KoolCenter 的固件）。
# 所以输入和产物都放在草稿 Release 里：草稿只有对仓库有写权限的人看得到。
#
# 在电脑上:
#   rogui/ci.sh run <KoolCenter 固件.pkgtb> [原厂固件.zip]
#       把两个固件传到草稿 Release「inputs」（同名同大小的不重传），触发 workflow，等它跑完，
#       把产物下载到 rogui/dist/ci-<编号>/。原厂固件不写时用项目目录里最新的 FW_GT-BE98_Pro_*.zip。
#       仓库默认取当前目录的 GitHub 仓库，也可以用 REPO=owner/name 指定。
# workflow 里用（一般不用手动跑）:
#   rogui/ci.sh fetch <KoolCenter 文件名> <原厂文件名> <下载目录>
#   rogui/ci.sh publish <产物目录> [其他文件...]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
INPUTS_TAG=inputs
WORKFLOW=bake.yml

die() { echo "❌ $*" >&2; exit 1; }

REPO="${REPO:-${GITHUB_REPOSITORY:-}}"
if [ -z "${REPO}" ]; then
	REPO="$(cd "${PROJECT_DIR}" && gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
fi
[ -n "${REPO}" ] || die "不知道是哪个 GitHub 仓库：在仓库目录里跑，或者设 REPO=owner/name"

# 草稿 Release 的 id（按 tag 名找；草稿的 tag 在发布前不会真的创建）
draft_id() {
	gh api "repos/${REPO}/releases?per_page=100" --paginate \
		--jq ".[] | select(.draft and .tag_name == \"$1\") | .id" | head -1
}

# 不登录也能看到的 Release 里不能有这个 tag，否则就是公开的了
assert_not_public() {
	local n
	n="$(curl -fsS "https://api.github.com/repos/${REPO}/releases?per_page=100" | grep -c "\"tag_name\": *\"$1\"" || true)"
	[ "${n}" = 0 ] || die "Release「$1」不登录也能看到，说明它不是草稿。立刻在网页上删掉或改回草稿"
}

asset_size() {  # $1 release id, $2 文件名 → 大小，没有则空
	gh api "repos/${REPO}/releases/$1/assets?per_page=100" --paginate \
		--jq ".[] | select(.name == \"$2\") | .size" | head -1
}

upload() {  # $1 release id, $2 文件
	local name
	name="$(basename "$2")"
	gh api -X POST "https://uploads.github.com/repos/${REPO}/releases/$1/assets?name=${name}" \
		-H 'Content-Type: application/octet-stream' --input "$2" --jq .name > /dev/null
}

download() {  # $1 release id, $2 文件名, $3 目录
	local id
	id="$(gh api "repos/${REPO}/releases/$1/assets?per_page=100" --paginate --jq ".[] | select(.name == \"$2\") | .id" | head -1)"
	[ -n "${id}" ] || die "草稿 Release 里没有 $2"
	mkdir -p "$3"
	gh api -H 'Accept: application/octet-stream' "repos/${REPO}/releases/assets/${id}" > "$3/$2"
}

cmd_fetch() {
	local rid
	rid="$(draft_id "${INPUTS_TAG}")"
	[ -n "${rid}" ] || die "没有草稿 Release「${INPUTS_TAG}」，先在电脑上跑 rogui/ci.sh run"
	download "${rid}" "$1" "$3"
	download "${rid}" "$2" "$3"
	ls -l "$3"
}

cmd_publish() {
	local dir="$1"; shift
	local tag="bake-${GITHUB_RUN_NUMBER:?只在 workflow 里用}"
	local notes="${dir}/notes.md"
	{
		echo "workflow 第 ${GITHUB_RUN_NUMBER} 次运行：${GITHUB_SERVER_URL}/${REPO}/actions/runs/${GITHUB_RUN_ID}"
		echo
		echo '```'
		cat "${dir}"/*.verify.txt
		echo
		cat "${dir}"/*.sha256
		echo '```'
	} > "${notes}"
	local rid
	rid="$(gh api -X POST "repos/${REPO}/releases" -f tag_name="${tag}" -f name="${tag}" -F draft=true \
		-F body=@"${notes}" --jq .id)"
	for f in "${dir}"/*.pkgtb "${dir}"/*.verify.txt "${dir}"/*.sha256 "$@"; do
		[ -f "${f}" ] && upload "${rid}" "${f}" && echo "已上传 $(basename "${f}")"
	done
	assert_not_public "${tag}"
	echo "产物在草稿 Release「${tag}」"
}

cmd_run() {
	local kc="$1" stock="${2:-}"
	[ -f "${kc}" ] || die "文件不存在: ${kc}"
	if [ -z "${stock}" ]; then
		stock="$(ls "${PROJECT_DIR}"/FW_GT-BE98_Pro_*.zip 2>/dev/null | sort | tail -1)"
		[ -n "${stock}" ] || die "没找到原厂固件，请作为第二个参数传入"
	fi
	[ -f "${stock}" ] || die "文件不存在: ${stock}"
	echo "== 仓库: ${REPO}"

	local rid
	rid="$(draft_id "${INPUTS_TAG}")"
	if [ -z "${rid}" ]; then
		rid="$(gh api -X POST "repos/${REPO}/releases" -f tag_name="${INPUTS_TAG}" -f name="${INPUTS_TAG}" \
			-F draft=true -f body='bake.yml 的输入固件。保持草稿状态，不要发布：发布就等于公开重新分发固件。' --jq .id)"
		echo "已建草稿 Release「${INPUTS_TAG}」"
	fi
	for f in "${kc}" "${stock}"; do
		local name size have
		name="$(basename "${f}")"
		size="$(wc -c < "${f}" | tr -d ' ')"
		have="$(asset_size "${rid}" "${name}")"
		if [ "${have}" = "${size}" ]; then
			echo "已在草稿里: ${name}"
		else
			[ -z "${have}" ] || die "草稿里已有同名但大小不同的 ${name}，先在网页上删掉它"
			echo "上传 ${name}（$((size / 1048576))MB）..."
			upload "${rid}" "${f}"
		fi
	done
	assert_not_public "${INPUTS_TAG}"

	local since
	since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	gh workflow run "${WORKFLOW}" -R "${REPO}" -f kc="$(basename "${kc}")" -f stock="$(basename "${stock}")"
	local run=""
	for _ in $(seq 1 30); do
		run="$(gh run list -R "${REPO}" -w "${WORKFLOW}" -e workflow_dispatch -L 5 --json databaseId,createdAt \
			--jq "[.[] | select(.createdAt >= \"${since}\")][0].databaseId // empty")"
		[ -n "${run}" ] && break
		sleep 2
	done
	[ -n "${run}" ] || die "找不到刚触发的 workflow 运行"
	echo "== 运行: https://github.com/${REPO}/actions/runs/${run}"
	gh run watch "${run}" -R "${REPO}" --exit-status > /dev/null || die "workflow 失败，看上面的链接"

	local num tag out
	num="$(gh run view "${run}" -R "${REPO}" --json number --jq .number)"
	tag="bake-${num}"
	out="${SCRIPT_DIR}/dist/ci-${num}"
	rid="$(draft_id "${tag}")"
	[ -n "${rid}" ] || die "没找到产物草稿 Release「${tag}」"
	for name in $(gh api "repos/${REPO}/releases/${rid}/assets?per_page=100" --paginate --jq '.[].name'); do
		download "${rid}" "${name}" "${out}"
	done
	echo "== 产物已下载到 ${out}"
	( cd "${out}" && shasum -a 256 -c ./*.pkgtb.sha256 )
	sed -n '/全部通过\|有检查没通过/p' "${out}"/*.verify.txt
}

case "${1:-}" in
	run) shift; [ $# -ge 1 ] || die "用法: $0 run <KoolCenter 固件.pkgtb> [原厂固件.zip]"; cmd_run "$@" ;;
	fetch) shift; [ $# -eq 3 ] || die "用法: $0 fetch <KoolCenter 文件名> <原厂文件名> <下载目录>"; cmd_fetch "$@" ;;
	publish) shift; [ $# -ge 1 ] || die "用法: $0 publish <产物目录> [其他文件...]"; cmd_publish "$@" ;;
	*) sed -n '2,16p' "$0"; exit 1 ;;
esac
