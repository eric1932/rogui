#!/bin/bash
# 用 GitHub Actions 把 rogui 做进固件（.github/workflows/bake.yml）。需要 gh 并已登录。
#
# 输入的两个固件放在草稿 Release「inputs」里，只有对仓库有写权限的人看得到。
# 产物放进 Release「rogui-<KoolCenter 版本>-<重新打包日期>」，例如 rogui-3006_102.8_0-20261107。同名的已经有了，
# 就在后面加 -r<运行编号>。产物默认是草稿；仓库变量 ROGUI_RELEASE=public，或者 run 时加 --public，才发布成
# 公开 Release。公开 Release 谁都能下载，等于公开分发华硕和 KoolCenter 的固件，fork 的人自己决定要不要这样做。
#
# 在电脑上:
#   rogui/ci.sh run [--public|--draft] <KoolCenter 固件.pkgtb> [原厂固件.zip]
#       把两个固件传到草稿 Release「inputs」（同名同大小的不重传），触发 workflow，等它跑完，
#       把产物下载到 rogui/dist/ci-<编号>/。原厂固件不写时用项目目录里最新的 FW_GT-BE98_Pro_*.zip。
#       补丁包里文件的修改时间是打包时刻，所以 CI 的固件和本地的不会逐字节相同；要核对的话，
#       拿 CI 的补丁包在本地 bake 一次，sha256 应该和 CI 的固件一样。
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

# 不管是不是草稿，有没有用这个 tag 名的 Release
release_exists() {
	[ -n "$(gh api "repos/${REPO}/releases?per_page=100" --paginate \
		--jq ".[] | select(.tag_name == \"$1\") | .id" | head -1)" ]
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
	[ -n "${id}" ] || die "Release 里没有 $2"
	mkdir -p "$3"
	gh api -H 'Accept: application/octet-stream' "repos/${REPO}/releases/assets/${id}" > "$3/$2"
}

sha256_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$1" | cut -d' ' -f1; }

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
	local run_url="${GITHUB_SERVER_URL:-https://github.com}/${REPO}/actions/runs/${GITHUB_RUN_ID:?只在 workflow 里用}"
	local mode="${ROGUI_RELEASE:-draft}"
	case "${mode}" in draft|public) ;; *) die "ROGUI_RELEASE 只能是 draft 或 public，现在是 ${mode}" ;; esac

	local pkg name kcver date stockver
	pkg="$(ls "${dir}"/*.pkgtb 2>/dev/null | head -1)"
	[ -n "${pkg}" ] || die "${dir} 里没有 .pkgtb"
	name="$(basename "${pkg}" .pkgtb)"
	# 文件名形如 GT-BE98_PRO_3006_102.8_0_nand_squashfs-20260710-0756872-rogui-20261107-stock39441
	kcver="$(printf '%s' "${name}" | sed -n 's/^.*_PRO_\(.*\)_nand_.*$/\1/p')"
	date="$(printf '%s' "${name}" | sed -n 's/^.*-rogui-\([0-9]\{8\}\)-.*$/\1/p')"
	stockver="$(printf '%s' "${name}" | sed -n 's/^.*-rogui-[0-9]\{8\}-stock\(.*\)$/\1/p')"
	[ -n "${kcver}" ] && [ -n "${date}" ] || die "看不懂产物文件名 ${name}，没法起 Release 名"

	local tag="rogui-${kcver}-${date}"
	release_exists "${tag}" && tag="${tag}-r${GITHUB_RUN_NUMBER}"
	local title="rogui ${kcver}（重新打包 ${date:0:4}-${date:4:2}-${date:6:2}）"

	# 产物目录是 sudo bake.sh 建的，属于 root，说明写到临时文件
	local notes in_dir="${INPUT_DIR:-in}"
	notes="$(mktemp)"
	{
		echo "**非官方**：GT-BE98 Pro 的 KoolCenter 梅林改版固件，换上了华硕原厂 ROG 网页（rogui 固件版）。不是 KoolCenter 或华硕出品。"
		echo
		echo "> Unofficial build: the KoolCenter firmware for GT-BE98 Pro with ASUS's stock ROG web UI baked in. Only \`/www\` in the root filesystem differs from the original."
		echo
		if [ -n "${KC:-}" ] && [ -f "${in_dir}/${KC}" ]; then
			echo "- 原版固件：\`${KC}\`（sha256 \`$(sha256_of "${in_dir}/${KC}")\`），只替换了根文件系统里的 \`/www\`"
		fi
		if [ -n "${STOCK:-}" ] && [ -f "${in_dir}/${STOCK}" ]; then
			echo "- ROG 网页来自原厂固件 \`${STOCK}\`（sha256 \`$(sha256_of "${in_dir}/${STOCK}")\`）"
		elif [ -n "${stockver}" ]; then
			echo "- ROG 网页来自原厂固件 102_${stockver}"
		fi
		echo "- 重新打包：${date:0:4}-${date:4:2}-${date:6:2}，[workflow 第 ${GITHUB_RUN_NUMBER} 次运行](${run_url})，代码提交 \`${GITHUB_SHA:0:7}\`"
		echo "- 怎么刷、刷完要部署 \`rogui.sh\`、怎么撤回：见仓库 README 的「固件版」"
		echo "- 版权方对这里分发的文件有异议，请提 issue，会尽快撤下"
		echo
		echo '<details><summary>逐项对比报告和 sha256</summary>'
		echo
		echo '```'
		cat "${dir}"/*.verify.txt
		echo
		cat "${dir}"/*.sha256
		echo '```'
		echo
		echo '</details>'
	} > "${notes}"

	# 先建成草稿，文件都传完再公开，避免出现只有一半文件的公开 Release
	local rid
	rid="$(gh api -X POST "repos/${REPO}/releases" -f tag_name="${tag}" -f target_commitish="${GITHUB_SHA}" \
		-f name="${title}" -F draft=true -F body=@"${notes}" --jq .id)"
	for f in "${dir}"/*.pkgtb "${dir}"/*.verify.txt "${dir}"/*.sha256 "$@"; do
		[ -f "${f}" ] && upload "${rid}" "${f}" && echo "已上传 $(basename "${f}")"
	done

	local url="${GITHUB_SERVER_URL:-https://github.com}/${REPO}/releases/tag/${tag}"
	if [ "${mode}" = public ]; then
		gh api -X PATCH "repos/${REPO}/releases/${rid}" -F draft=false > /dev/null
		curl -fsS -o /dev/null "https://api.github.com/repos/${REPO}/releases/tags/${tag}" \
			|| die "Release「${tag}」已经设成公开，但不登录还看不到"
		echo "产物已公开发布：${url}"
	else
		assert_not_public "${tag}"
		url="${GITHUB_SERVER_URL:-https://github.com}/${REPO}/releases（草稿「${tag}」，登录后才看得到）"
		echo "产物在草稿 Release「${tag}」"
	fi
	[ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "**Release：** ${url}" >> "${GITHUB_STEP_SUMMARY}"
	return 0
}

cmd_run() {
	local release=""
	case "${1:-}" in
		--public) release=public; shift ;;
		--draft) release=draft; shift ;;
	esac
	[ $# -ge 1 ] || die "用法: $0 run [--public|--draft] <KoolCenter 固件.pkgtb> [原厂固件.zip]"
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
			-F draft=true -f body='bake.yml 的输入固件。保持草稿状态，不要发布。' --jq .id)"
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
	local args=(-f kc="$(basename "${kc}")" -f stock="$(basename "${stock}")")
	[ -n "${release}" ] && args+=(-f release="${release}")
	gh workflow run "${WORKFLOW}" -R "${REPO}" "${args[@]}"
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

	# 产物 Release 的说明里带着这次运行的链接，按它找
	local num out info tag draft
	num="$(gh run view "${run}" -R "${REPO}" --json number --jq .number)"
	out="${SCRIPT_DIR}/dist/ci-${num}"
	info="$(gh api "repos/${REPO}/releases?per_page=100" --paginate \
		--jq ".[] | select((.body // \"\") | contains(\"/actions/runs/${run})\")) | \"\(.id) \(.tag_name) \(.draft)\"" | head -1)"
	[ -n "${info}" ] || die "没找到这次运行的产物 Release"
	read -r rid tag draft <<< "${info}"
	for name in $(gh api "repos/${REPO}/releases/${rid}/assets?per_page=100" --paginate --jq '.[].name'); do
		download "${rid}" "${name}" "${out}"
	done
	echo "== 产物已下载到 ${out}"
	( cd "${out}" && shasum -a 256 -c ./*.pkgtb.sha256 )
	grep -hE '全部通过|有检查没通过' "${out}"/*.verify.txt
	if [ "${draft}" = true ]; then
		echo "== Release「${tag}」是草稿，只有你登录后看得到"
	else
		echo "== 已公开发布: https://github.com/${REPO}/releases/tag/${tag}"
	fi
}

case "${1:-}" in
	run) shift; cmd_run "$@" ;;
	fetch) shift; [ $# -eq 3 ] || die "用法: $0 fetch <KoolCenter 文件名> <原厂文件名> <下载目录>"; cmd_fetch "$@" ;;
	publish) shift; [ $# -ge 1 ] || die "用法: $0 publish <产物目录> [其他文件...]"; cmd_publish "$@" ;;
	*) sed -n '2,18p' "$0"; exit 1 ;;
esac
