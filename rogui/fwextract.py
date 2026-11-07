#!/usr/bin/env python3
"""从华硕固件文件里直接拆出 /www（以及单个文件），不需要路由器。

支持:
  - .pkgtb（KoolCenter / 梅林 / 原厂的 FIT 镜像）
  - .zip（华硕官网下载的原厂固件包，里面套着一个 .pkgtb）
  - .tar.gz（以前从路由器上 `tar czf - /www` 拉下来的打包，原样读取）

命令行:
  python3 -I fwextract.py www <固件> <输出.tar.gz>     拆出 /www，格式和路由器上 tar 出来的一样
  python3 -I fwextract.py file <固件> <路径> <输出>     拆出单个文件，例如 /usr/sbin/httpd
  python3 -I fwextract.py fp <固件或www.tar.gz>         打印 /www 指纹（和 rogui.sh 在路由器上算的一致）
"""
import hashlib
import io
import os
import struct
import sys
import tarfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sqfs  # noqa: E402  同目录的纯标准库 squashfs 读取器


def _image_bytes(path):
    if path.endswith('.zip'):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith('.pkgtb')]
            if len(names) != 1:
                raise SystemExit('%s 里应该恰好有一个 .pkgtb，实际: %s' % (path, names))
            return z.read(names[0])
    with open(path, 'rb') as f:
        return f.read()


def _rootfs(data):
    """在镜像里找最大的 squashfs v4（根文件系统）。"""
    best = None
    i = 0
    while True:
        i = data.find(b'hsqs', i)
        if i < 0:
            break
        try:
            vmaj, vmin = struct.unpack_from('<HH', data, i + 28)
            used = struct.unpack_from('<Q', data, i + 40)[0]
            if (vmaj, vmin) == (4, 0) and (best is None or used > best[1]):
                best = (i, used)
        except struct.error:
            pass
        i += 4
    if best is None:
        raise SystemExit('镜像里没找到 squashfs 根文件系统')
    return sqfs.Sqfs(io.BytesIO(data), best[0])


def is_firmware(path):
    return path.endswith(('.pkgtb', '.zip'))


def model(path):
    """FIT 镜像根节点的 description，华硕在这里放机型名（例如 GT-BE98_PRO）。不是固件或解析不了时返回 None。"""
    if not is_firmware(path):
        return None
    if path.endswith('.zip'):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith('.pkgtb')]
            if len(names) != 1:
                return None
            with z.open(names[0]) as f:
                data = f.read(65536)
    else:
        with open(path, 'rb') as f:
            data = f.read(65536)
    try:
        magic, _, off_struct, off_strings = struct.unpack_from('>IIII', data, 0)
        if magic != 0xd00dfeed or struct.unpack_from('>I', data, off_struct)[0] != 1:
            return None
        p = (data.index(b'\0', off_struct + 4) + 4) & ~3   # 跳过根节点名
        while True:
            tag = struct.unpack_from('>I', data, p)[0]
            p += 4
            if tag == 4:          # FDT_NOP
                continue
            if tag != 3:          # 不是属性（到子节点了）
                return None
            ln, nameoff = struct.unpack_from('>II', data, p)
            p += 8
            name = data[off_strings + nameoff:data.index(b'\0', off_strings + nameoff)]
            if name == b'description':
                return data[p:p + ln].rstrip(b'\0').decode('ascii', 'replace')
            p = (p + ln + 3) & ~3
    except (struct.error, ValueError):
        return None


def open_fs(path):
    return _rootfs(_image_bytes(path))


def www_tree(fs, prefix='/www'):
    """返回 ({相对路径: 内容}, {相对路径: 链接目标})，相对路径不带 www/ 前缀。"""
    files, links = {}, {}
    for p, ino in fs.walk():
        if not p.startswith(prefix + '/'):
            continue
        rel = p[len(prefix) + 1:]
        if ino['type'] in (2, 9):
            files[rel] = fs.read_file(ino)
        elif ino['type'] in (3, 10):
            links[rel] = ino['target']
    if 'state.js' not in files:
        raise SystemExit('镜像里的 %s 没有 state.js，不像是华硕固件' % prefix)
    return files, links


def read_one(fs, path):
    for p, ino in fs.walk():
        if p == path and ino['type'] in (2, 9):
            return fs.read_file(ino)
    raise SystemExit('镜像里没有 %s' % path)


def fingerprint(files, links):
    """/www 指纹。算法必须和 rogui.sh 的 www_fp() 逐字节一致：
    先按 C 语言排序列出每个文件的 "md5  ./路径"，再列出每个链接的 "./路径 -> 目标"，整体取 md5。"""
    h = hashlib.md5()
    for p in sorted(files, key=lambda s: s.encode()):
        h.update(('%s  ./%s\n' % (hashlib.md5(files[p]).hexdigest(), p)).encode())
    for p in sorted(links, key=lambda s: s.encode()):
        h.update(('./%s -> %s\n' % (p, links[p])).encode())
    return h.hexdigest()


def write_www_tar(files, links, out):
    with tarfile.open(out, 'w:gz') as t:
        for p in sorted(files):
            info = tarfile.TarInfo('www/' + p)
            info.size = len(files[p])
            info.mode = 0o644
            t.addfile(info, io.BytesIO(files[p]))
        for p in sorted(links):
            info = tarfile.TarInfo('www/' + p)
            info.type = tarfile.SYMTYPE
            info.linkname = links[p]
            t.addfile(info)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, src = sys.argv[1], sys.argv[2]
    if cmd == 'www':
        files, links = www_tree(open_fs(src))
        write_www_tar(files, links, sys.argv[3])
        print('%d 个文件，%d 个链接 → %s' % (len(files), len(links), sys.argv[3]))
    elif cmd == 'file':
        data = read_one(open_fs(src), sys.argv[3])
        with open(sys.argv[4], 'wb') as f:
            f.write(data)
        print('%s %d 字节 → %s' % (sys.argv[3], len(data), sys.argv[4]))
    elif cmd == 'fp':
        if is_firmware(src):
            files, links = www_tree(open_fs(src))
        else:
            spec = __import__('importlib.util').util.spec_from_file_location('build', os.path.join(HERE, 'build.py'))
            build = __import__('importlib.util').util.module_from_spec(spec)
            spec.loader.exec_module(build)
            files, links = build.load_tree(src)
        print(fingerprint(files, links))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
