#!/usr/bin/env python3
"""静态检查合成后的 /www：找出"合并后才出现"的断链和后端不支持的调用。

用法:
  python3 -I check.py --stock <原厂固件> --kc <KoolCenter 固件> --pkg dist/rogui-<名字>.tgz

--kc 是固件文件时，httpd 直接从固件里拆；--kc 是 /www 的 tar.gz 时，要另外用 --httpd 指定
（可以从路由器只读拉取：ssh admin@192.168.50.1 'cat /usr/sbin/httpd' > httpd）。
有需要人工判断的问题时退出码为 1。

合成后的 /www = KoolCenter 原版 + overlay − 补丁包 remove.txt 里的文件（build.py --slim 删掉的）。

检查项（都只报告"原厂或 KoolCenter 单独运行时没有、合并后才出现"的问题）:
  1. 引用了不存在的文件（会 404）。指向精简时故意删掉的文件的，单独列出，不算问题
  2. 原厂页面调用了 KoolCenter httpd 里没有的 <% 函数 %>（输出为空；不在引号里时会变成 JS 语法错误）
  3. 原厂页面请求了 KoolCenter httpd 不处理的 .cgi
  4. 字典编号超出字典行数
"""
import argparse
import importlib.util
import io
import os
import re
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('build', os.path.join(HERE, 'build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

TEXT = ('.asp', '.htm', '.html', '.js', '.css', '.json', '.xml')
ASSET = r'(?:asp|htm|html|js|css|png|gif|jpg|jpeg|svg|json|xml|ico|woff|woff2|otf|ttf)'
REF_ATTR = re.compile(r'''(?:src|href|action)\s*=\s*["']([^"'#?\s]+)''', re.I)
REF_CSS = re.compile(r'''url\(\s*["']?([^"')?#\s]+)''')
REF_STR = re.compile(r'''["']([\w./-]+\.%s)["']''' % ASSET)
HOOK = re.compile(r'<%\s*(\w+)\s*\(')
APPGET = re.compile(r'hook=(\w+)\(')
# 不能写成 ["'/]?([\w-]+...)：在 css/json 里的长串 base64 上会退化成平方复杂度，check 一半时间耗在这
CGI = re.compile(r'''(?<![\w-])([\w-]+\.cgi)\b''')
TOKEN = re.compile(r'<#(\d+)#>')
SKIP_PREFIX = ('res/', 'ext/', 'user/', '_api', '_temp', '_root', '_resp', '_result', '_upload', 'Module_')


def load_overlay(pkg):
    with tarfile.open(pkg) as t:
        m = t.getmember('rogui/overlay.tgz')
        data = t.extractfile(m).read()
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t.getmembers():
            if m.isfile():
                out[m.name] = t.extractfile(m).read()
    return out


def load_remove(pkg):
    """补丁包里的删除清单；旧包没有这个文件，就是空的。"""
    with tarfile.open(pkg) as t:
        try:
            data = t.extractfile('rogui/remove.txt').read()
        except KeyError:
            return set()
    return {l for l in data.decode('utf-8').split('\n') if l}


def ref_targets(path, r):
    """引用 r（出现在 path 里）可能指向的文件，和 refs() 的候选算法一致。"""
    if r.startswith('/'):
        return [os.path.normpath(r.lstrip('/'))]
    return [os.path.normpath(os.path.join(os.path.dirname(path), r)), os.path.normpath(r)]


def refs(path, text):
    """返回 (原始引用, 候选路径列表)。"""
    d = os.path.dirname(path)
    found = []
    for rx in (REF_ATTR, REF_CSS, REF_STR):
        for r in rx.findall(text):
            if any(x in r for x in ('<%', '+', '$', '{', '\\')) or '://' in r or r.startswith(('//', 'data:', 'javascript:', 'mailto:')):
                continue
            if r.endswith('.cgi') or not re.search(r'\.%s$' % ASSET, r, re.I):
                continue
            cands = []
            if r.startswith('/'):
                cands.append(os.path.normpath(r.lstrip('/')))
            else:
                cands.append(os.path.normpath(os.path.join(d, r)))
                cands.append(os.path.normpath(r))
            found.append((r, cands))
    return found


def missing_refs(files, links):
    names = set(files) | set(links)
    dirs = {os.path.dirname(n) for n in names}
    out = set()
    for path, data in files.items():
        if not path.endswith(TEXT):
            continue
        text = data.decode('utf-8', 'ignore')
        for r, cands in refs(path, text):
            if any(c.startswith(SKIP_PREFIX) or c.split('/')[0] in links for c in cands):
                continue
            if not any(c in names or c in dirs for c in cands):
                out.add((path, r))
    return out


class Binary:
    """在 httpd 二进制里查名字：函数名要求以 \\0 结尾，cgi 允许是 mime 模式的一部分。"""

    def __init__(self, data):
        self.data = data

    def has_func(self, name):
        # 链接器会做字符串尾部合并（"nvram_get" 可能只存在于 "ej_nvram_get\0" 的尾部），所以只要求以 \0 结尾
        return (name.encode() + b'\x00') in self.data

    def has_cgi(self, name):
        return name.encode() in self.data


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--stock', required=True)
    ap.add_argument('--kc', required=True)
    ap.add_argument('--pkg', required=True)
    ap.add_argument('--httpd', help='KoolCenter 的 /usr/sbin/httpd；--kc 是固件文件时可省略')
    args = ap.parse_args()

    st, st_links = build.load_tree(args.stock)
    kc, kc_links = build.load_tree(args.kc)
    ov = load_overlay(args.pkg)
    removed = load_remove(args.pkg)
    merged = dict(kc)
    merged.update(ov)
    for n in removed:
        merged.pop(n, None)
    kc_links_merged = {n: v for n, v in kc_links.items() if n not in removed}
    origin = {n: ('stock' if (n in st and merged[n] == st[n]) or (n in ov and n in st and not build.prefer_kc(n)) else 'kc') for n in merged}
    if args.httpd:
        with open(args.httpd, 'rb') as f:
            hs = Binary(f.read())
    elif build.fwextract.is_firmware(args.kc):
        hs = Binary(build.fwextract.read_one(build.fwextract.open_fs(args.kc), '/usr/sbin/httpd'))
    else:
        sys.exit('check.py: --kc 不是固件文件时必须用 --httpd 指定 httpd')
    # 原厂 httpd：原厂自己也不支持的函数/cgi 不是合并引入的（例如给别的机型用的 AFC、AI board 接口）
    st_hs = None
    if build.fwextract.is_firmware(args.stock):
        st_hs = Binary(build.fwextract.read_one(build.fwextract.open_fs(args.stock), '/usr/sbin/httpd'))
    problems = 0

    # 1. 断链
    new = missing_refs(merged, kc_links_merged) - missing_refs(st, st_links) - missing_refs(kc, kc_links)
    slimmed = {(p, r) for p, r in new if any(c in removed for c in ref_targets(p, r))}
    new -= slimmed
    print('== 1. 合并后新出现的断链（%d 处）' % len(new))
    for path, r in sorted(new):
        print('   %s -> %s' % (path, r))
    problems += len(new)
    if removed:
        print('== 1b. 指向精简时故意删掉的文件（%d 处，删除清单 %d 项；预期如此，不算问题）' % (len(slimmed), len(removed)))
        for path, r in sorted(slimmed):
            print('   %s -> %s' % (path, r))

    # 2/3. 原厂来源的页面调用 KoolCenter httpd 没有的函数 / cgi
    # KoolCenter 自己的页面也这样用的，不算合并引入的问题
    kc_lines = set()
    kc_cgis = set()
    for n, data in kc.items():
        if n.endswith(TEXT):
            text = data.decode('utf-8', 'ignore')
            kc_lines.update(l.strip() for l in text.split('\n') if '<%' in l)
            kc_cgis.update(CGI.findall(text))
    must_fix, harmless = [], []
    bad_cgi = {}
    for n, data in merged.items():
        if origin[n] != 'stock' or not n.endswith(TEXT):
            continue
        text = data.decode('utf-8', 'ignore')
        for line in text.split('\n'):
            for mo in HOOK.finditer(line):
                name = mo.group(1)
                if hs.has_func(name) or (st_hs and not st_hs.has_func(name)):
                    continue
                # 输出为空时会不会变成 JS 语法错误：只有"裸用在表达式里"才会，例如 x = <% f(); %>;
                bare = re.search(r'[=:(,]\s*<%%\s*%s\s*\([^%%]*%%>\s*[;,)]' % re.escape(name), line)
                item = (name, n, line.strip()[:100])
                if bare and line.strip() not in kc_lines:
                    must_fix.append(item)
                else:
                    harmless.append(item)
        for name in set(CGI.findall(text)):
            if not hs.has_cgi(name) and name not in kc_cgis and (st_hs is None or st_hs.has_cgi(name)):
                bad_cgi.setdefault(name, []).append(n)
    print('== 2a. 原厂页面裸用了 KoolCenter httpd 里没有的函数，会导致 JS 语法错误（%d 处）' % len(must_fix))
    for name, n, line in must_fix:
        print('   %s @ %s: %s' % (name, n, line))
    names = sorted({h[0] for h in harmless})
    print('== 2b. 同样没有、但不会报错的（包在 [] 或引号里，或 KoolCenter 自己也这么用）: %d 处，涉及 %s' % (len(harmless), ', '.join(names)))
    print('== 3. 只有原厂页面请求、KoolCenter httpd 不处理的 .cgi（%d 个；点到相关功能时会失败）' % len(bad_cgi))
    for name in sorted(bad_cgi):
        pages = sorted(set(bad_cgi[name]))
        print('   %s: %s' % (name, ', '.join(pages[:6]) + (' 等 %d 个' % len(pages) if len(pages) > 6 else '')))
    problems += len(must_fix) + len(bad_cgi)

    # 4. 字典编号越界
    n_lines = len(merged['EN.dict'].decode('utf-8').split('\n')) - 1
    over = sorted({(n, int(t)) for n, d in merged.items() if n.endswith(TEXT)
                   for t in TOKEN.findall(d.decode('utf-8', 'ignore')) if int(t) >= n_lines})
    print('== 4. 字典编号越界（%d 处，字典 %d 行）' % (len(over), n_lines))
    for n, t in over[:20]:
        print('   %s: <#%d#>' % (n, t))
    problems += len(over)

    print('共 %d 项需要人工判断' % problems)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
