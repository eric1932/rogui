#!/usr/bin/env python3
"""rogui 自测：按 golden.json 的黄金标准重跑一遍，确认代码没改坏。只在 Mac 上跑，不碰路由器。

用法:
  python3 -I selftest.py            # 固件文件默认在上一级目录（项目根目录）
  python3 -I selftest.py --fw-dir <放固件的目录>

缺少的固件文件会跳过并提示，不算失败。全部通过退出码 0，否则 1。
"""
import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fx = load('fwextract')
results = []


def report(ok, what, detail=''):
    results.append(ok)
    mark = {True: '✅', False: '❌', None: '⏭ '}[ok]
    print('%s %s%s' % (mark, what, ('  ' + detail) if detail else ''))


def overlay_hash(pkg):
    with tarfile.open(pkg) as t:
        ov = t.extractfile('rogui/overlay.tgz').read()
        built_for = t.extractfile('rogui/built_for').read().decode().strip()
    files = {}
    with tarfile.open(fileobj=io.BytesIO(ov)) as t:
        for m in t.getmembers():
            if m.isfile():
                files[m.name] = t.extractfile(m).read()
    return fx.fingerprint(files, {}), len(files), built_for


def run(args):
    return subprocess.run([sys.executable, '-I'] + args, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fw-dir', default=os.path.dirname(HERE))
    args = ap.parse_args()
    with open(os.path.join(HERE, 'golden.json'), encoding='utf-8') as f:
        golden = json.load(f)
    fw = lambda name: os.path.join(args.fw_dir, name)

    print('== 1. 固件 /www 指纹')
    for name, g in golden['firmware'].items():
        if not os.path.exists(fw(name)):
            report(None, name, '没有这个文件，跳过')
            continue
        files, links = fx.www_tree(fx.open_fs(fw(name)))
        got = (fx.fingerprint(files, links), len(files), len(links))
        report(got == (g['www_fp'], g['files'], g['links']), name, '' if got[0] == g['www_fp'] else '实际 %s' % (got,))

    print('== 2. 拼补丁包（内容哈希、文件数、配套指纹、包名）')
    with tempfile.TemporaryDirectory() as tmp:
        for b in golden['builds']:
            what = b['label']
            if not (os.path.exists(fw(b['kc'])) and os.path.exists(fw(b['stock']))):
                report(None, what, '缺固件文件，跳过')
                continue
            out = os.path.join(tmp, what)
            r = run([os.path.join(HERE, 'build.py'), '--stock', fw(b['stock']), '--kc', fw(b['kc']), '--out', out])
            pkg = os.path.join(out, 'rogui-%s.tgz' % b['label'])
            if r.returncode != 0 or not os.path.exists(pkg):
                report(False, what, 'build 失败: ' + (r.stderr.strip() or r.stdout.strip())[-200:])
                continue
            h, n, built_for = overlay_hash(pkg)
            want_fp = golden['firmware'][b['kc']]['www_fp']
            ok = (h, n, built_for) == (b['overlay_hash'], b['overlay_files'], want_fp)
            report(ok, what, '' if ok else '实际 哈希=%s 文件=%d 配套=%s' % (h, n, built_for))
            if b.get('check'):
                c = run([os.path.join(HERE, 'check.py'), '--stock', fw(b['stock']), '--kc', fw(b['kc']), '--pkg', pkg])
                report(c.returncode == 0, what + ' 静态检查', c.stdout.strip().splitlines()[-1] if c.stdout.strip() else c.stderr.strip()[-200:])

        print('== 3. 反例（必须报错，且不能产出补丁包）')
        for neg in golden['negative']:
            out = os.path.join(tmp, 'neg')
            r = run([os.path.join(HERE, 'build.py'), '--stock', fw(neg['stock']), '--kc', fw(neg['kc']), '--out', out])
            msg = (r.stderr + r.stdout)
            produced = os.path.isdir(out) and any(n.endswith('.tgz') for n in os.listdir(out))
            ok = r.returncode != 0 and neg['expect'] in msg and not produced
            report(ok, neg['name'], '' if ok else '退出码 %d，输出: %s' % (r.returncode, msg.strip()[-200:]))

    print('== 4. 路由器上合成后 /www 的指纹应为 %s（手动核对，见 TESTING.md）' % golden['router']['merged_www_fp'])
    failed = results.count(False)
    print('\n通过 %d，失败 %d，跳过 %d' % (results.count(True), failed, results.count(None)))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
