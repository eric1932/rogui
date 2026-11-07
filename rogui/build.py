#!/usr/bin/env python3
"""把原厂 ROG /www 合成为能叠加在 KoolCenter /www 上的补丁包。

用法:
  python3 -I build.py --stock <原厂固件> --kc <KoolCenter 固件> [--label 名字] [--out dist/]

两个输入都可以是固件文件（.pkgtb，或华硕官网下载的 .zip），直接从里面拆 /www；
也可以是以前在路由器上 `tar czf - /www` 打出来的 .tar.gz。
输出 dist/rogui-<名字>.tgz，里面是 overlay.tgz + rogui.sh + built_for + manifest.json，
解压到路由器 /jffs/rogui/ 后用 rogui.sh start|stop|status 控制。

路由器上的做法: 开机把 KoolCenter 自己的 /www 复制到 /tmp 当底板，
解开 overlay.tgz 覆盖上去，再 mount --bind 到 /www。所以 overlay 里只放
"和 KoolCenter 不一样的部分"，相同的文件不重复存。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fwextract  # noqa: E402

# 这些页面两边都有，但用 KoolCenter(Merlin) 的版本：原厂的 VPN Fusion 和 VPN Director 冲突
PREFER_KC = {
    'Advanced_VPN_OpenVPN.asp',
    'Advanced_VPNServer_Content.asp',
    'Advanced_VPNClient_Content.asp',
    'Advanced_OpenVPNClient_Content.asp',
    'Advanced_WireguardClient_Content.asp',
    'Advanced_WireguardServer_Content.asp',
    # 只被上面这些 Merlin 页面用到的 ajax：原厂版 ajax_coretmp 调用的 get_fanctrl_info 在 Merlin 里没编译，会输出语法错误
    'ajax_coretmp.asp',
    'ajax_openvpn_server.asp',
}

# 整个目录都用 KoolCenter 版：VPN/ 是 VPN 客户端/服务器页内嵌的 VPN Fusion 视图，要和 KoolCenter 后端配套
PREFER_KC_DIRS = ('VPN/',)


def prefer_kc(n):
    return n in PREFER_KC or n.startswith(PREFER_KC_DIRS)


# 往原厂菜单里补的 Merlin 页面: (菜单 index, 插在哪个 url 后面 / None=插在 __INHERIT__ 前, [要补的 url])
MENU_INSERTS = [
    ('menu_GameBoost', None, ['QoS_Stats.asp']),
    ('menu_TrafficAnalyzer', 'Main_TrafficMonitor_daily.asp',
     ['Main_TrafficMonitor_monthly.asp', 'Main_TrafficMonitor_settings.asp']),
    ('menu_LAN', None, ['DNSDirector.asp']),
    ('menu_Setting', None, ['Advanced_SNMP_Content.asp', 'Tools_OtherSettings.asp']),
    ('menu_NekworkTool', None, ['Advanced_Wireless_Survey.asp']),
]
# 整块换成 KoolCenter 版本的菜单
MENU_REPLACE = ['menu_VPN']
# 追加到菜单末尾的 KoolCenter 菜单块（顺序即显示顺序；软件中心必须是最后一项）
MENU_APPEND = ['menu_Sysinfo', 'menu_Split@last', 'menu_Softcenter']

# 原厂 bug：首页和电竞仪表板的频段图标，把各主网络（MAINFH）的频段掩码相加。
# 两个主网络带同一位（如 6G 通用位 16）时会进位，把 6G-1(32)/6G-2(64) 冲掉，射频在发也显示灭。改成按位或
BAND_OR_PAGES = ('index.asp', 'GameDashboard.asp')
BAND_SUM = b'mainFHNum += wifi_band;'
BAND_OR = b'mainFHNum |= wifi_band;'

EXTRA_CSS = b"""
.menu_Sysinfo{
\tbackground-image: url(images/New_ui/icon_menues.png);
\tbackground-position: -0px -126px;
}
.menu_Softcenter{
\tbackground: url(images/New_ui/softcenter.png);
\tbackground-position: 0px 0px;
}
"""

MODEL = 'GT-BE98_PRO'  # FIT 镜像根节点 description 里的机型名

TEXT_EXT = ('.asp', '.js', '.html', '.htm', '.json', '.css', '.xml')
TOKEN = re.compile(rb'<#(\d+)#>')


def die(msg):
    sys.exit('build.py: ' + msg)


def load_tree(path):
    if fwextract.is_firmware(path):
        return fwextract.www_tree(fwextract.open_fs(path))
    files, links = {}, {}
    with tarfile.open(path) as t:
        for m in t.getmembers():
            n = m.name
            if n.startswith('./'):
                n = n[2:]
            n = n.lstrip('/')
            if n == 'www' or not n.startswith('www/'):
                continue
            n = n[4:]
            if m.issym():
                links[n] = m.linkname
            elif m.isfile():
                files[n] = t.extractfile(m).read()
    if 'state.js' not in files:
        die('%s 里没有 www/state.js，不像是 /www 的打包' % path)
    return files, links


def split_lines(b):
    return b.decode('utf-8').split('\n')


class DictRemap:
    """KoolCenter 页面里的 <#N#> 是 KoolCenter 字典的行号，换成原厂字典后要重新映射。"""

    def __init__(self, kc, st):
        self.kc = {l: split_lines(kc[l + '.dict']) for l in ('EN', 'CN', 'TW')}
        self.langs = sorted(n[:-5] for n in st if n.endswith('.dict') and '/' not in n)
        self.st = {l: split_lines(st[l + '.dict']) for l in self.langs}
        counts = {l: len(v) for l, v in self.st.items()}
        if len(set(counts.values())) != 1:
            die('原厂各语言字典行数不一致: %s' % counts)
        # 文件以换行结尾，split 后最后一项是空串；新行要插在它前面
        self.n = counts['EN'] - 1
        self.index = {}
        for i in range(self.n):
            key = tuple(self.st[l][i].rstrip('\r') for l in ('EN', 'CN', 'TW'))
            self.index.setdefault(key, i)
        self.memo = {}
        self.appended = 0
        self.used = 0

    def map(self, n):
        if n in self.memo:
            return self.memo[n]
        key = tuple(self.kc[l][n].rstrip('\r') for l in ('EN', 'CN', 'TW'))
        m = self.index.get(key)
        if m is None:
            m = self.n
            for l in self.langs:
                src = self.kc[l] if l in self.kc else self.kc['EN']
                self.st[l].insert(self.n, src[n].rstrip('\r'))
            self.n += 1
            self.index[key] = m
            self.appended += 1
        self.memo[n] = m
        return m

    def apply(self, data):
        def sub(mo):
            self.used += 1
            return b'<#%d#>' % self.map(int(mo.group(1)))
        return TOKEN.sub(sub, data)

    def dict_files(self):
        return {l + '.dict': '\n'.join(self.st[l]).encode('utf-8') for l in self.langs}


def menu_block(lines, index):
    """返回菜单块 [start, end) 行号：start 是 '{'，end 是块的收尾 '}' 或 '},' 那一行之后。"""
    hits = [i for i, s in enumerate(lines) if s.strip() == 'index: "%s",' % index]
    if not hits:
        return None
    i = hits[0]
    start = i
    while lines[start].strip() != '{':
        start -= 1
    depth = 0
    for j in range(start, len(lines)):
        depth += lines[j].count('{') - lines[j].count('}')
        if depth == 0:
            return start, j + 1
    die('菜单 %s 的大括号不配对' % index)


def menu_last_block(lines, index):
    """同名菜单块有多个（menu_Split）时取最后一个。"""
    hits = [i for i, s in enumerate(lines) if s.strip() == 'index: "%s",' % index]
    if not hits:
        return None
    sub = lines[:]
    for h in hits[:-1]:
        sub[h] = '/* skipped */'
    return menu_block(sub, index)


def find_tab_line(lines, start, end, url):
    for k in range(start, end):
        if '{url: "%s"' % url in lines[k]:
            return k
    return None


def patch_menu(st_js, kc_js, remap, files, report):
    st = split_lines(st_js)
    # 只有从 KoolCenter 搬过来的行要重映射字典编号，原厂自己的行不能动
    kc = [remap.apply(s.encode('utf-8')).decode('utf-8') for s in split_lines(kc_js)]
    # KoolCenter 菜单里指向不存在页面的项（它靠自己的 exclude 规则隐藏，原厂的 exclude 不认识）直接去掉
    dropped = []
    for k, line in enumerate(kc):
        m = re.search(r'\{url: "([^"<]+\.(?:asp|htm|html))"', line)
        # Module_*.asp 是软件中心的页面，由 httpd 从 /koolshare/webs 读，不在 /www 里
        if m and m.group(1) not in files and not m.group(1).startswith('Module_'):
            dropped.append(m.group(1))
            kc[k] = None
    kc = [line for line in kc if line is not None]
    if dropped:
        report.append('菜单: 去掉指向不存在页面的项 %s' % ', '.join(sorted(set(dropped))))

    for index in MENU_REPLACE:
        sb, kb = menu_block(st, index), menu_block(kc, index)
        if not sb or not kb:
            die('菜单 %s 在某一边找不到' % index)
        new = kc[kb[0]:kb[1]]
        if st[sb[1] - 1].rstrip().endswith(',') and not new[-1].rstrip().endswith(','):
            new[-1] = new[-1].rstrip() + ','
        st[sb[0]:sb[1]] = new
        report.append('菜单 %s: 整块换成 KoolCenter 版' % index)

    for index, after, urls in MENU_INSERTS:
        blk = menu_block(st, index)
        if not blk:
            report.append('跳过 %s: 原厂菜单里没有这个菜单' % index)
            continue
        add = []
        for u in urls:
            k = find_tab_line(kc, 0, len(kc), u)
            if k is None:
                report.append('跳过 %s: KoolCenter 菜单里没有' % u)
            elif find_tab_line(st, blk[0], blk[1], u) is not None:
                report.append('跳过 %s: 原厂 %s 里已有' % (u, index))
            else:
                add.append(kc[k].strip())
        if not add:
            continue
        if after:
            pos = find_tab_line(st, blk[0], blk[1], after)
            if pos is None:
                die('在原厂 %s 里找不到锚点 %s' % (index, after))
            pos += 1
        else:
            pos = find_tab_line(st, blk[0], blk[1], 'NULL')
            if pos is None:
                die('原厂 %s 里没有 NULL/__INHERIT__ 收尾行' % index)
        st[pos:pos] = add
        report.append('菜单 %s: 加 %s' % (index, ', '.join(re.findall(r'url: "([^"]+)"', ' '.join(add)))))

    # 菜单列表的收尾: 最后一个菜单块后面跟着 '],' 和 'exclude: {'
    ex = [i for i, s in enumerate(st) if s.strip() == 'exclude: {']
    if len(ex) != 1 or st[ex[0] - 1].strip() != '],':
        die('原厂 menuTree.js 结构变了：找不到 "],\\nexclude: {"')
    close = ex[0] - 1
    last = close - 1
    if st[last].strip() != '}':
        die('原厂 menuTree.js 最后一个菜单块不是以 } 结尾')
    blocks = []
    for spec in MENU_APPEND:
        index = spec.split('@')[0]
        kb = menu_last_block(kc, index) if spec.endswith('@last') else menu_block(kc, index)
        if not kb:
            die('KoolCenter 菜单里没有 %s' % index)
        b = kc[kb[0]:kb[1]]
        b[-1] = b[-1].rstrip().rstrip(',')
        blocks.append(b)
    ins = []
    for i, b in enumerate(blocks):
        if i < len(blocks) - 1:
            b = b[:-1] + [b[-1] + ',']
        ins += b
    st[last] = st[last].rstrip() + ','
    st[close:close] = ins
    report.append('菜单末尾追加: %s（软件中心保持最后一项）' % ', '.join(s.split('@')[0] for s in MENU_APPEND))

    return '\n'.join(st).encode('utf-8')


STATE_TRY = 'try{\nshowMenuTree(Session.get("menuList." + ui_lang), Session.get("menuExclude"));'
STATE_END = '\nsetTimeout(function(){\nif (typeof httpApi'


def show_menu_tail(js):
    f = js.find('function show_menu(){')
    if f < 0:
        return None, None
    a = js.find('try{', f)
    b = js.find(STATE_END, a)
    if a < 0 or b < 0:
        return None, None
    return a, b


def patch_state(st_js, kc_js, remap, report):
    st = st_js.decode('utf-8')
    kc = remap.apply(kc_js).decode('utf-8')
    if 'menu_hook' in st:
        die('原厂 state.js 里已经有 menu_hook，输入是不是弄反了？')
    a, b = show_menu_tail(st)
    ka, kb = show_menu_tail(kc)
    if a is None or ka is None:
        die('state.js 里找不到 show_menu 的 try/catch 段')
    if not st[a:].startswith(STATE_TRY):
        die('原厂 show_menu 的 try 段和预期不一样，需要人工核对')
    hook = kc[ka:kb]
    if 'menu_hook' not in hook:
        die('KoolCenter show_menu 里没有 menu_hook，软件中心挂钩方式可能变了')
    st = st[:a] + hook + st[b:]
    decl = 'var tabtitle = [""];\nvar tablink = [""];\n'
    if decl not in kc:
        die('KoolCenter state.js 里没有 tabtitle/tablink 声明')
    st = st.replace('function show_menu(){', decl + 'function show_menu(){', 1)
    report.append('state.js: 换入 KoolCenter 的 show_menu 挂钩，加 tabtitle/tablink 声明')
    return st.encode('utf-8')


def patch_band_or(name, data, report):
    n = data.count(BAND_SUM)
    if n == 1:
        report.append('%s: 频段图标的掩码相加改成按位或' % name)
        return data.replace(BAND_SUM, BAND_OR)
    if n == 0 and BAND_OR in data:
        report.append('%s: 原厂已经是按位或，不用改' % name)
    else:
        report.append('警告: %s 里频段掩码相加的那行有 %d 处（预期 1 处），没改' % (name, n))
    return data


FUNC_DEF = re.compile(r'(?:function\s+([A-Za-z_$][\w$]*)\s*\(|([A-Za-z_$][\w$]*)\s*=\s*function\b|(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=)')
SCRIPT_SRC = re.compile(r'<script[^>]+src="/?([^"?]+)')


def js_defs(text):
    return {a or b or c for a, b, c in FUNC_DEF.findall(text)}


def compat_gaps(st, kc, kept, overlay):
    """找出留用的 KoolCenter 页面调用、但原厂版公共 js 里没有定义的函数。返回 {js 路径: [函数名]}。"""
    gaps = {}
    for page in kept:
        if not page.endswith(('.asp', '.html')):
            continue
        text = kc[page].decode('utf-8', 'ignore')
        own = js_defs(text)
        for inc in set(SCRIPT_SRC.findall(text)):
            if inc not in kc or inc not in st or kc[inc] == st[inc]:
                continue
            have = js_defs(overlay.get(inc, st[inc]).decode('utf-8', 'ignore'))
            missing = js_defs(kc[inc].decode('utf-8', 'ignore')) - have - own
            for n in missing:
                if len(n) > 3 and re.search(r'\b%s\s*\(' % re.escape(n), text):
                    gaps.setdefault(inc, set()).add(n)
    return {k: sorted(v) for k, v in gaps.items()}


def extract_function(js, name):
    """摘出 `function name(...) {...}` 的完整源码（按大括号配对，不处理字符串里的括号）。"""
    m = re.search(r'(?m)^[ \t]*function\s+%s\s*\(' % re.escape(name), js)
    if not m:
        return None
    i = js.index('{', m.end())
    depth = 0
    for j in range(i, len(js)):
        if js[j] == '{':
            depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0:
                return js[m.start():j + 1].strip()
    return None


def default_label(kc_path, stock_path, fp):
    """包名 = KoolCenter 版本 + 原厂版本，例如 3006_102.8_0-stock39441。
    两个版本都要带上：同一版 KoolCenter 配不同的原厂网页，拼出来的补丁不一样。"""
    m = re.search(r'_(\d{4}_\d+\.\d+_\d+)', os.path.basename(kc_path))
    label = m.group(1) if m else fp[:12]
    s = re.search(r'(?:3006102|102_)(\d{5})', os.path.basename(stock_path))
    return label + ('-stock' + s.group(1) if s else '')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--stock', required=True, help='原厂固件（.zip/.pkgtb）或原厂 /www 的 tar.gz')
    ap.add_argument('--kc', required=True, help='KoolCenter 固件（.pkgtb）或 KoolCenter /www 的 tar.gz')
    ap.add_argument('--label', help='补丁包名字，默认从 KoolCenter 固件文件名里取版本')
    ap.add_argument('--icon', default=os.path.join(HERE, 'assets', 'softcenter_rog.png'),
                    help='软件中心菜单图标，默认用 GT-BE96 官改的 ROG 配色版本')
    ap.add_argument('--out', default=os.path.join(HERE, 'dist'))
    args = ap.parse_args()

    # 输入核对：机型对不对、原厂和 KoolCenter 有没有放反或放错
    for path, what in ((args.stock, '--stock'), (args.kc, '--kc')):
        m = fwextract.model(path)
        if m is not None and m != MODEL:
            die('%s 是 %s 的固件，不是 %s' % (what, m, MODEL))
    st, st_links = load_tree(args.stock)
    kc, kc_links = load_tree(args.kc)
    if 'Tools_Sysinfo.asp' in st or 'AdaptiveQoS_ROG.asp' not in st:
        die('--stock 不像华硕原厂 ROG 固件（有 Merlin 页面或缺 ROG 页面），是不是把 Merlin/KoolCenter 固件当成原厂了？')
    if 'Tools_Sysinfo.asp' not in kc or b'menu_hook' not in kc['state.js']:
        die('--kc 不像 KoolCenter 固件（没有 Merlin 页面，或 state.js 里没有软件中心挂钩 menu_hook）')
    # 补丁包只适用于这一版 KoolCenter /www：路由器上的 rogui.sh 会算同样的指纹，对不上就不启用
    kc_fp = fwextract.fingerprint(kc, kc_links)
    report = []

    remap = DictRemap(kc, st)
    overlay = {}

    # 1. 原厂文件：和 KoolCenter 不同的、或 KoolCenter 没有的
    same = 0
    for n, data in st.items():
        if prefer_kc(n) and n in kc:
            continue
        if n.endswith('.dict') and '/' not in n:
            continue  # 字典最后统一写
        if kc.get(n) == data:
            same += 1
            continue
        overlay[n] = data
    report.append('原厂文件: %d 个与 KoolCenter 相同(不存), %d 个放进补丁' % (same, len(overlay)))

    # 2. 留用 KoolCenter 版本的文件：底板里已经有，只有含 <#N#> 的需要重映射后覆盖
    kept = [n for n in kc if n not in st or prefer_kc(n)]
    remapped = 0
    for n in kept:
        data = kc[n]
        if n.endswith('.dict'):
            continue
        if n.endswith(TEXT_EXT) and b'<#' in data:
            new = remap.apply(data)
            if new != data:
                overlay[n] = new
                remapped += 1
    report.append('KoolCenter 独有/保留的文件 %d 个，其中 %d 个重映射了字典编号' % (len(kept), remapped))

    # 2b. Merlin 页面调用的公共函数，原厂版 js 里可能没有：从 KoolCenter 版里摘出来补到末尾
    for inc, names in compat_gaps(st, kc, kept, overlay).items():
        base = overlay.get(inc, st[inc])
        add = [extract_function(kc[inc].decode('utf-8', 'ignore'), n) for n in names]
        add = [a for a in add if a]
        if not add:
            report.append('警告: %s 缺 %s，但没能从 KoolCenter 版里摘出来' % (inc, ', '.join(names)))
            continue
        overlay[inc] = base + ('\n/* rogui: 从 KoolCenter 版补入，Merlin 页面要用 */\n' + '\n'.join(add) + '\n').encode('utf-8')
        report.append('%s: 补入 %s' % (inc, ', '.join(names)))

    # 3. 菜单、state.js、样式、图标
    overlay['require/modules/menuTree.js'] = patch_menu(st['require/modules/menuTree.js'],
                                                        kc['require/modules/menuTree.js'], remap,
                                                        set(st) | set(kc), report)
    overlay['state.js'] = patch_state(st['state.js'], kc['state.js'], remap, report)
    for n in BAND_OR_PAGES:
        if n in st and not prefer_kc(n):
            overlay[n] = patch_band_or(n, overlay.get(n, st[n]), report)
    overlay['index_style.css'] = st['index_style.css'] + EXTRA_CSS
    if os.path.exists(args.icon):
        with open(args.icon, 'rb') as f:
            overlay['images/New_ui/softcenter.png'] = f.read()
        report.append('软件中心图标: %s' % os.path.relpath(args.icon, HERE))
    else:
        report.append('软件中心图标: 没找到 %s，沿用 KoolCenter 自带的' % args.icon)

    # 4. 字典（含新追加的行）
    overlay.update(remap.dict_files())
    report.append('字典: 映射 %d 处编号，原厂字典里没有、追加了 %d 条' % (remap.used, remap.appended))

    # 5. 符号链接：底板是 KoolCenter 的 /www，链接沿用它的；这里只核对 res 在
    if kc_links.get('res') != '/jffs/.koolshare/res':
        report.append('警告: KoolCenter /www/res 不是指向 /jffs/.koolshare/res: %r' % kc_links.get('res'))

    # 打包
    os.makedirs(args.out, exist_ok=True)
    tag = args.label or default_label(args.kc, args.stock, kc_fp)
    built_for = kc_fp + '\n'
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', compresslevel=9) as t:
        for n in sorted(overlay):
            info = tarfile.TarInfo(n)
            info.size = len(overlay[n])
            info.mtime = int(time.time())
            info.mode = 0o644
            t.addfile(info, io.BytesIO(overlay[n]))
    overlay_tgz = buf.getvalue()

    manifest = {
        'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'label': tag,
        'kc_www_fingerprint': kc_fp,
        'stock_input': os.path.basename(args.stock),
        'kc_input': os.path.basename(args.kc),
        'overlay_files': len(overlay),
        'overlay_sha256': hashlib.sha256(overlay_tgz).hexdigest(),
        'report': report,
    }
    pkg = os.path.join(args.out, 'rogui-%s.tgz' % tag)
    with tarfile.open(pkg, 'w:gz') as t:
        def add(name, data, mode=0o644):
            info = tarfile.TarInfo('rogui/' + name)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = mode
            t.addfile(info, io.BytesIO(data))
        add('overlay.tgz', overlay_tgz)
        with open(os.path.join(HERE, 'rogui.sh'), 'rb') as f:
            add('rogui.sh', f.read(), 0o755)
        add('built_for', built_for.encode())
        add('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=1).encode('utf-8'))

    for line in report:
        print('  ' + line)
    print('overlay.tgz %.1f MB, %d 个文件' % (len(overlay_tgz) / 1e6, len(overlay)))
    print('输出: %s' % pkg)


if __name__ == '__main__':
    main()
