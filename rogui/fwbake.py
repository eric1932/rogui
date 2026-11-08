#!/usr/bin/env python3
"""把 rogui 的 ROG 网页直接做进 KoolCenter 固件（.pkgtb）的辅助工具，只用标准库。

.pkgtb 是 FIT 镜像：开头是设备树格式的头，后面紧跟各段数据。头里每段记着 data-offset（从头的末尾、
按 4 字节对齐处算起）、data-size 和 sha256，没有签名。这里只换掉根文件系统（squashfs）那一段：
原地改它的 data-size 和 sha256，头的其他字节和前面的启动分区一个字节都不动。

子命令:
  split  <固件.pkgtb> <输出目录>
         校验每段的 sha256，把根文件系统拆成 <输出目录>/rootfs.sqfs，打印各段和 squashfs 参数（JSON）
  pack   <原固件.pkgtb> <新 rootfs.sqfs> <输出.pkgtb>
         换掉根文件系统，改头里的大小和 sha256，写完再整体校验一遍
  fp     <www 目录>
         算目录的 /www 指纹，算法和 rogui.sh 的 www_fp()、fwextract.fingerprint() 一致
  verify <原固件.pkgtb> <新固件.pkgtb> <原 rootfs 解开的目录> <新 rootfs 解开的目录> <rogui 补丁包.tgz>
         逐项对比：/www 以外的每个文件、目录、链接、设备文件完全相同；新 /www 等于"原版 /www + overlay − 补丁包 remove.txt 里的文件"；
         打印新 /www 的指纹和刷进路由器要占的 UBI 块数。全部通过退出码 0，否则 1
  blocks <固件.pkgtb> [正在跑的固件.pkgtb]
         打印刷进路由器要占多少 UBI 块；给了正在跑的固件，就算一下这次能不能一次刷完
"""
import hashlib
import io
import json
import os
import stat
import struct
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fwextract  # noqa: E402  同目录：用纯 Python 的 squashfs 读取器再独立读一遍新固件

FDT_MAGIC = 0xd00dfeed
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
SQFS_FLAGS = ['UNCOMPRESSED_INODES', 'UNCOMPRESSED_DATA', 'CHECK', 'UNCOMPRESSED_FRAGMENTS', 'NO_FRAGMENTS',
              'ALWAYS_FRAGMENTS', 'DUPLICATES', 'EXPORTABLE', 'UNCOMPRESSED_XATTRS', 'NO_XATTRS',
              'COMPRESSOR_OPTIONS', 'UNCOMPRESSED_IDS']
SQFS_COMP = {1: 'gzip', 2: 'lzma', 3: 'lzo', 4: 'xz', 5: 'lz4', 6: 'zstd'}

# 刷进路由器占多少 UBI 块（报告 10，GT-BE98 Pro 实测）：刷机库给每段建卷，块数 = ceil(字节 / 126976) + 9。
# 两个号位加空闲一共 1332 块，刷机写的是备用号位，所以"正在跑的 + 新的 ≤ 1332"。
# 每个固件不超过一半，从固件版升级到固件版才能一次刷完。别的机器可以用环境变量 ROGUI_UBI_POOL 改总数
UBI_LEB = 126976
UBI_EXTRA = 9
UBI_POOL = int(os.environ.get('ROGUI_UBI_POOL', '1332'))


def ubi_blocks(sizes):
    return sum(-(-s // UBI_LEB) + UBI_EXTRA for s in sizes)


def ubi_report(orig_sizes, new_sizes):
    """打印新固件占多少块，超过一半时提醒（只是提醒，不算检查失败）。"""
    a, b, half = ubi_blocks(orig_sizes), ubi_blocks(new_sizes), UBI_POOL // 2
    print('ℹ️  刷进路由器占 %d 个 UBI 块（原版 %d）；两个号位加空闲共 %d 块，一半是 %d' % (b, a, UBI_POOL, half))
    if b <= half:
        print('✅ 不超过一半：备用号位里放的也是这么大的固件时，一次就能刷完')
    elif b <= UBI_POOL - a:
        print('⚠️  超过一半 %d 块：正在跑的也是固件版时可能放不下，要先刷 KoolCenter 原版、再刷这个。'
              '用 --slim 精简能变小（报告 10）' % (b - half))
    else:
        print('⚠️  太大：另一个号位放原版时也只剩 %d 块，放不下这个固件。先用 --slim 精简（报告 10）' % (UBI_POOL - a))


def die(msg):
    raise SystemExit('❌ ' + msg)


# ---------- FIT 头 ----------

def fit_props(d):
    """返回 (头的总长, 数据区起点, {'images/xxx/data-size': (值在文件里的偏移, 长度)})。根节点的属性键名不带斜杠。"""
    if len(d) < 40:
        die('文件太短，不是固件')
    (magic, totalsize, off_struct, off_strings, _rsv, _ver, _lcv, _cpu,
     sz_strings, sz_struct) = struct.unpack_from('>10I', d, 0)
    if magic != FDT_MAGIC:
        die('开头不是设备树（FIT），不是 .pkgtb 固件')
    strings = d[off_strings:off_strings + sz_strings]
    props, path = {}, []
    i, end = off_struct, off_struct + sz_struct
    while i < end:
        tok, = struct.unpack_from('>I', d, i)
        i += 4
        if tok == FDT_BEGIN_NODE:
            e = d.index(b'\0', i)
            path.append(d[i:e].decode())
            i = (e + 4) & ~3
        elif tok == FDT_END_NODE:
            path.pop()
        elif tok == FDT_PROP:
            ln, no = struct.unpack_from('>II', d, i)
            i += 8
            name = strings[no:strings.index(b'\0', no)].decode()
            props['/'.join(path[1:] + [name])] = (i, ln)
            i = (i + ln + 3) & ~3
        elif tok == FDT_NOP:
            pass
        elif tok == FDT_END:
            break
        else:
            die('FIT 头解析失败：未知标记 %d' % tok)
    return totalsize, (totalsize + 3) & ~3, props


def prop_str(d, props, key):
    off, ln = props[key]
    return bytes(d[off:off + ln]).rstrip(b'\0').decode()


def prop_u32(d, props, key):
    off, ln = props[key]
    if ln != 4:
        die('%s 长度是 %d，不是 4 字节' % (key, ln))
    return struct.unpack_from('>I', d, off)[0]


def fit_images(d):
    """解析并校验 FIT：返回 (数据区起点, props, 段列表, 根文件系统段名)。每段都核对 sha256。"""
    _, base, props = fit_props(d)
    names = sorted({k.split('/')[1] for k in props if k.startswith('images/') and k.count('/') >= 2})
    imgs = []
    for n in names:
        p = 'images/%s/' % n
        if p + 'data-offset' not in props or p + 'data-size' not in props:
            die('段 %s 不是外置数据（没有 data-offset/data-size），不支持' % n)
        off, size = prop_u32(d, props, p + 'data-offset'), prop_u32(d, props, p + 'data-size')
        algo = prop_str(d, props, p + 'hash-1/algo') if p + 'hash-1/algo' in props else None
        if algo != 'sha256':
            die('段 %s 的校验算法是 %s，只支持 sha256' % (n, algo))
        hoff, hlen = props[p + 'hash-1/value']
        want = bytes(d[hoff:hoff + hlen])
        got = hashlib.sha256(d[base + off:base + off + size]).digest()
        if base + off + size > len(d) or got != want:
            die('段 %s 的 sha256 对不上，固件文件可能损坏或被截断' % n)
        imgs.append({'name': n, 'offset': off, 'size': size, 'sha256': got.hex(),
                     'type': prop_str(d, props, p + 'type') if p + 'type' in props else ''})
    imgs.sort(key=lambda x: x['offset'])
    conf = prop_str(d, props, 'configurations/default')
    rootfs = prop_str(d, props, 'configurations/%s/rootfs' % conf)
    if rootfs not in names:
        die('配置 %s 指向的根文件系统段 %s 不存在' % (conf, rootfs))
    if any(k.startswith('images/%s/signature' % rootfs) for k in props) or any('/signature' in k for k in props):
        die('固件里有签名节点，改了会通不过校验，不支持')
    return base, props, imgs, rootfs


def sqfs_info(b):
    (magic, inodes, mkfs_time, block_size, frags, comp, _blog, flags, ids, vmaj, vmin,
     _root, bytes_used, _idt, xattr_t) = struct.unpack_from('<IIIIIHHHHHHQQQQ', b, 0)
    if magic != 0x73717368 or (vmaj, vmin) != (4, 0):
        die('根文件系统不是 squashfs 4.0')
    info = {'comp': SQFS_COMP.get(comp, comp), 'block_size': block_size, 'mkfs_time': mkfs_time,
            'flags': [n for i, n in enumerate(SQFS_FLAGS) if flags & (1 << i)], 'inodes': inodes,
            'bytes_used': bytes_used, 'has_xattrs': xattr_t != 0xffffffffffffffff, 'comp_opts': None}
    if flags & (1 << 10):
        hdr, = struct.unpack_from('<H', b, 96)
        info['comp_opts'] = bytes(b[98:98 + (hdr & 0x7fff)]).hex()
    return info


def cmd_split(path, outdir):
    d = open(path, 'rb').read()
    base, props, imgs, rootfs = fit_images(d)
    last = imgs[-1]
    if last['name'] != rootfs:
        die('根文件系统不是最后一段，换了它会挪动后面的段，不支持')
    if base + last['offset'] + last['size'] != len(d):
        die('文件末尾还有 %d 字节不属于任何段，不认识，不支持' % (len(d) - base - last['offset'] - last['size']))
    r = next(x for x in imgs if x['name'] == rootfs)
    os.makedirs(outdir, exist_ok=True)
    blob = d[base + r['offset']:base + r['offset'] + r['size']]
    with open(os.path.join(outdir, 'rootfs.sqfs'), 'wb') as f:
        f.write(blob)
    print(json.dumps({'model': prop_str(d, props, 'description'), 'header_len': base, 'images': imgs,
                      'rootfs': rootfs, 'sqfs': sqfs_info(blob)}, ensure_ascii=False, indent=1))


def cmd_pack(orig, sqfs_path, out):
    d = bytearray(open(orig, 'rb').read())
    base, props, imgs, rootfs = fit_images(d)
    r = next(x for x in imgs if x['name'] == rootfs)
    if imgs[-1]['name'] != rootfs or base + r['offset'] + r['size'] != len(d):
        die('原固件的布局不是"根文件系统在最后、后面没有别的数据"，不支持')
    new = open(sqfs_path, 'rb').read()
    sqfs_info(new)
    off, ln = props['images/%s/data-size' % rootfs]
    struct.pack_into('>I', d, off, len(new))
    hoff, hlen = props['images/%s/hash-1/value' % rootfs]
    if hlen != 32:
        die('sha256 值长度不是 32 字节')
    d[hoff:hoff + 32] = hashlib.sha256(new).digest()
    blob = bytes(d[:base + r['offset']]) + new
    fit_images(blob)  # 写之前再完整校验一遍
    with open(out, 'wb') as f:
        f.write(blob)
    print('输出: %s（%d 字节，根文件系统 %d → %d 字节）' % (out, len(blob), r['size'], len(new)))


# ---------- 目录对比 ----------

def www_fp_dir(www):
    files, links = {}, {}
    for dp, dns, fns in os.walk(www):
        for n in dns + fns:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, www)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                links[rel] = os.readlink(p)
            elif stat.S_ISREG(st.st_mode):
                with open(p, 'rb') as f:
                    files[rel] = f.read()
    return fwextract.fingerprint(files, links), files, links


def scan(root, skip_children_of=None):
    """{相对路径: 元数据元组}。skip_children_of='www' 时 www/ 下面的东西不收（www 目录自己收）。"""
    out = {}

    def entry(p, rel):
        st = os.lstat(p)
        t = stat.S_IFMT(st.st_mode)
        m = [t, stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid]
        if stat.S_ISCHR(st.st_mode) or stat.S_ISBLK(st.st_mode):
            m.append(st.st_rdev)
        if stat.S_ISREG(st.st_mode):
            with open(p, 'rb') as f:
                m += [st.st_size, hashlib.sha256(f.read()).hexdigest()]
        elif stat.S_ISLNK(st.st_mode):
            m.append(os.readlink(p))
        m.append(int(st.st_mtime))
        out[rel] = tuple(m)

    entry(root, '.')
    for dp, dns, fns in os.walk(root):
        rel_dp = os.path.relpath(dp, root)
        if skip_children_of and (rel_dp == skip_children_of or rel_dp.startswith(skip_children_of + os.sep)):
            dns[:] = []
            continue
        for n in dns + fns:
            p = os.path.join(dp, n)
            entry(p, os.path.relpath(p, root))
    return out


def cmd_verify(orig, new, dir_a, dir_b, pkg):
    ok = True

    def check(cond, good, bad):
        nonlocal ok
        print(('✅ ' + good) if cond else ('❌ ' + bad))
        ok = ok and cond

    da, db = open(orig, 'rb').read(), open(new, 'rb').read()
    ba, pa, ia, ra = fit_images(da)
    bb, pb, ib, rb = fit_images(db)
    check(prop_str(da, pa, 'description') == prop_str(db, pb, 'description'),
          '机型名相同：%s' % prop_str(db, pb, 'description'), '机型名变了')
    check(ba == bb, 'FIT 头长度相同（%d 字节）' % bb, 'FIT 头长度变了：%d → %d' % (ba, bb))
    diff = [i for i in range(min(ba, bb)) if da[i] != db[i]]
    allowed = set()
    for k in ('images/%s/data-size' % ra, 'images/%s/hash-1/value' % ra):
        o, n = pa[k]
        allowed.update(range(o, o + n))
    check(set(diff) <= allowed, 'FIT 头只改了根文件系统的 data-size 和 sha256（%d 个字节）' % len(diff),
          'FIT 头里有别的字节被改了')
    for x, y in zip(ia, ib):
        if x['name'] != ra:
            check(x == y and da[ba + x['offset']:ba + x['offset'] + x['size']] == db[bb + y['offset']:bb + y['offset'] + y['size']],
                  '段 %s 原样保留（%d 字节）' % (x['name'], x['size']), '段 %s 变了' % x['name'])
    sa = next(x for x in ia if x['name'] == ra)
    sb = next(x for x in ib if x['name'] == rb)
    print('ℹ️  根文件系统 %.1fMB → %.1fMB（%+.1fMB），新包 %.1fMB' % (
        sa['size'] / 1048576, sb['size'] / 1048576, (sb['size'] - sa['size']) / 1048576, len(db) / 1048576))
    ubi_report([x['size'] for x in ia], [x['size'] for x in ib])
    qa = sqfs_info(da[ba + sa['offset']:])
    qb = sqfs_info(db[bb + sb['offset']:])
    # 实验：bake.sh 用 ROGUI_SQFS_BLOCK 换了块大小时，块大小要等于要求的值，其余参数照旧和原包比
    want_bs = int(os.environ.get('ROGUI_SQFS_BLOCK') or qa['block_size'])
    if want_bs != qa['block_size']:
        check(qb['block_size'] == want_bs, '⚠️ 实验：squashfs 块大小按要求从 %d 改成 %d' % (qa['block_size'], want_bs),
              'squashfs 块大小是 %d，要求的是 %d' % (qb['block_size'], want_bs))
    keys = ('comp', 'flags', 'has_xattrs', 'comp_opts', 'mkfs_time') + (() if want_bs != qa['block_size'] else ('block_size',))
    same = {k: (qa[k], qb[k]) for k in keys if qa[k] != qb[k]}
    check(not same, 'squashfs %s和原包相同（%s，块 %d，%s）' % (
              '除块大小以外的参数' if want_bs != qa['block_size'] else '参数', qb['comp'], qb['block_size'], '+'.join(qb['flags'])),
          'squashfs 参数和原包不同: %s' % same)

    # /www 以外：逐项相同
    A, B = scan(dir_a, 'www'), scan(dir_b, 'www')
    wa, wb = A.pop('www', None), B.pop('www', None)
    only_a, only_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))
    changed = sorted(k for k in set(A) & set(B) if A[k] != B[k])
    check(not (only_a or only_b or changed),
          '/www 以外 %d 项（文件、目录、链接、设备文件）的类型、权限、属主、设备号、内容、修改时间全部相同' % len(A),
          '/www 以外有差异：少了 %s，多了 %s，变了 %s' % (only_a[:5], only_b[:5], changed[:5]))
    check(wa is not None and wb is not None and wa[:4] == wb[:4],
          '/www 目录本身的类型、权限、属主不变', '/www 目录本身变了: %s → %s' % (wa, wb))

    # /www：等于 原版 + overlay − 删除清单（精简加的，旧补丁包没有）
    with tarfile.open(pkg) as t:
        ov = t.extractfile('rogui/overlay.tgz').read()
        built_for = t.extractfile('rogui/built_for').read().decode().strip()
        try:
            remove = [l for l in t.extractfile('rogui/remove.txt').read().decode('utf-8').split('\n') if l]
        except KeyError:
            remove = []
    fp_a, fa, la = www_fp_dir(os.path.join(dir_a, 'www'))
    check(fp_a == built_for, '原固件 /www 指纹 %s 和补丁包的 built_for 一致' % fp_a,
          '补丁包是给 %s 做的，这个固件的 /www 指纹是 %s' % (built_for, fp_a))
    want_f, want_l = dict(fa), dict(la)
    ov_modes = {}
    with tarfile.open(fileobj=io.BytesIO(ov)) as t:
        for m in t.getmembers():
            rel = os.path.normpath(m.name)
            if m.isfile():
                want_f[rel] = t.extractfile(m).read()
                want_l.pop(rel, None)
                ov_modes[rel] = (m.mode, m.uid, m.gid)
            elif m.issym():
                want_l[rel] = m.linkname
                want_f.pop(rel, None)
    for rel in remove:
        rel = os.path.normpath(rel)
        want_f.pop(rel, None)
        want_l.pop(rel, None)
    fp_b, fb, lb = www_fp_dir(os.path.join(dir_b, 'www'))
    what = '原版 /www + overlay' + (' − 删除清单 %d 项' % len(remove) if remove else '')
    check(fb.keys() == want_f.keys() and all(fb[k] == want_f[k] for k in fb) and lb == want_l,
          '新 /www 正好等于"%s"：%d 个文件、%d 个链接' % (what, len(fb), len(lb)),
          '新 /www 和"%s"对不上' % what)
    bad_meta = []
    for rel in fb:
        st = os.lstat(os.path.join(dir_b, 'www', rel))
        if rel in ov_modes:
            if (stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid) != ov_modes[rel]:
                bad_meta.append(rel)
        else:
            a = os.lstat(os.path.join(dir_a, 'www', rel))
            if (a.st_mode, a.st_uid, a.st_gid) != (st.st_mode, st.st_uid, st.st_gid):
                bad_meta.append(rel)
    check(not bad_meta, '新 /www 里每个文件的权限和属主：没改的和原版一样，overlay 的和补丁包里一样',
          '新 /www 里有文件权限或属主不对: %s' % bad_meta[:5])

    # 用纯 Python 的 squashfs 读取器从新固件文件本身再读一遍 /www
    files2, links2 = fwextract.www_tree(fwextract.open_fs(new))
    fp_c = fwextract.fingerprint(files2, links2)
    check(fp_c == fp_b, '另一个读取器（sqfs.py）直接读新固件，/www 指纹也是 %s' % fp_c,
          'sqfs.py 读出的指纹 %s 和解包目录的 %s 不一样' % (fp_c, fp_b))
    print('新固件 /www 指纹: %s' % fp_b)
    print('全部通过' if ok else '有检查没通过')
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if a[:1] == ['split'] and len(a) == 3:
        cmd_split(a[1], a[2])
    elif a[:1] == ['pack'] and len(a) == 4:
        cmd_pack(a[1], a[2], a[3])
    elif a[:1] == ['fp'] and len(a) == 2:
        print(www_fp_dir(a[1])[0])
    elif a[:1] == ['verify'] and len(a) == 6:
        sys.exit(cmd_verify(*a[1:]))
    elif a[:1] == ['blocks'] and len(a) in (2, 3):
        sizes = [[x['size'] for x in fit_images(open(p, 'rb').read())[2]] for p in a[1:]]
        n = ubi_blocks(sizes[0])
        print('%s: %d 块（一半是 %d）' % (os.path.basename(a[1]), n, UBI_POOL // 2))
        if len(a) == 3:
            room = UBI_POOL - ubi_blocks(sizes[1])
            print('正在跑 %s，留给备用号位 %d 块：%s' % (os.path.basename(a[2]), room,
                  '一次能刷完，剩 %d 块' % (room - n) if n <= room else '放不下，差 %d 块' % (n - room)))
    else:
        print(__doc__.strip())
        sys.exit(2)


if __name__ == '__main__':
    main()
