#!/usr/bin/env python3
"""Minimal read-only squashfs v4 reader (stdlib only).

usage:
  sqfs.py find  <image>                      -> print offsets of squashfs superblocks
  sqfs.py list  <image> <offset>             -> list all paths (type size path [-> target])
  sqfs.py extract <image> <offset> <outdir> <regex>
        extract regular files whose path matches regex; symlinks recorded in outdir/_symlinks.txt
"""
import sys, struct, zlib, lzma, os, re

COMP = {1: 'gzip', 2: 'lzma', 3: 'lzo', 4: 'xz', 5: 'lz4', 6: 'zstd'}


class Sqfs:
    def __init__(self, f, base):
        self.f = f
        self.base = base
        f.seek(base)
        sb = f.read(96)
        (self.magic, self.inode_count, _, self.block_size, self.frag_count, self.comp,
         _, self.flags, self.id_count, vmaj, vmin, self.root_inode, self.bytes_used,
         self.id_table, self.xattr_table, self.inode_table, self.dir_table,
         self.frag_table, self.export_table) = struct.unpack('<IIIIIHHHHHHQQQQQQQQ', sb)
        assert self.magic == 0x73717368, 'bad magic'
        assert (vmaj, vmin) == (4, 0), 'not v4'
        if self.comp not in (1, 2, 4):
            raise SystemExit('unsupported compressor %s' % COMP.get(self.comp))
        self.mcache = {}
        self._frags = None

    def decomp(self, data):
        if self.comp == 1:
            return zlib.decompress(data)
        if self.comp == 4:
            return lzma.decompress(data, format=lzma.FORMAT_XZ)
        if self.comp == 2:
            return lzma.decompress(data, format=lzma.FORMAT_ALONE)

    def rd(self, off, n):
        self.f.seek(self.base + off)
        return self.f.read(n)

    def mblock(self, off):
        """read metadata block at absolute (fs-relative) offset; return (data, next_off)"""
        if off in self.mcache:
            return self.mcache[off]
        hdr = struct.unpack('<H', self.rd(off, 2))[0]
        size = hdr & 0x7fff
        raw = self.rd(off + 2, size)
        data = raw if hdr & 0x8000 else self.decomp(raw)
        self.mcache[off] = (data, off + 2 + size)
        return self.mcache[off]

    def meta(self, table, blk, offset, n):
        """read n bytes of metadata starting at table+blk, offset; returns (bytes, (blk, offset) after)"""
        out = b''
        cur = table + blk
        data, nxt = self.mblock(cur)
        pos = offset
        while len(out) < n:
            if pos >= len(data):
                cur = nxt
                data, nxt = self.mblock(cur)
                pos = 0
            take = min(n - len(out), len(data) - pos)
            out += data[pos:pos + take]
            pos += take
        return out, (cur - table, pos)

    def frags(self):
        if self._frags is None:
            nblk = (self.frag_count * 16 + 8191) // 8192
            ptrs = struct.unpack('<%dQ' % nblk, self.rd(self.frag_table, 8 * nblk))
            ents = b''
            for p in ptrs:
                ents += self.mblock(p)[0]
            self._frags = [struct.unpack_from('<QII', ents, i * 16) for i in range(self.frag_count)]
        return self._frags

    def inode(self, ref):
        blk, off = ref >> 16, ref & 0xffff
        hdr, pos = self.meta(self.inode_table, blk, off, 16)
        itype, perm, uid, gid, mtime, ino = struct.unpack('<HHHHII', hdr)
        d = {'type': itype, 'perm': perm}
        if itype == 1:
            b, pos = self.meta(self.inode_table, *pos, 16)
            sb, lc, fsz, boff, par = struct.unpack('<IIHHI', b)
            d.update(dir_blk=sb, dir_off=boff, dir_size=fsz)
        elif itype == 8:
            b, pos = self.meta(self.inode_table, *pos, 24)
            lc, fsz, sb, par, icount, boff, xa = struct.unpack('<IIIIHHI', b)
            d.update(dir_blk=sb, dir_off=boff, dir_size=fsz)
        elif itype in (2, 9):
            if itype == 2:
                b, pos = self.meta(self.inode_table, *pos, 16)
                start, frag, foff, size = struct.unpack('<IIII', b)
            else:
                b, pos = self.meta(self.inode_table, *pos, 40)
                start, size, sparse, lc, frag, foff, xa = struct.unpack('<QQQIIII', b)
            if frag == 0xffffffff:
                nb = (size + self.block_size - 1) // self.block_size
            else:
                nb = size // self.block_size
            b, pos = self.meta(self.inode_table, *pos, 4 * nb)
            d.update(start=start, frag=frag, foff=foff, size=size, blocks=struct.unpack('<%dI' % nb, b))
        elif itype in (3, 10):
            b, pos = self.meta(self.inode_table, *pos, 8)
            lc, tsz = struct.unpack('<II', b)
            t, pos = self.meta(self.inode_table, *pos, tsz)
            d.update(target=t.decode('utf-8', 'replace'), size=tsz)
        return d

    def readdir(self, ino):
        size = ino['dir_size'] - 3
        if size <= 0:
            return []
        data, _ = self.meta(self.dir_table, ino['dir_blk'], ino['dir_off'], size)
        p = 0
        out = []
        while p < len(data):
            cnt, start, inum = struct.unpack_from('<IIi', data, p)
            p += 12
            for _ in range(cnt + 1):
                off, ioff, typ, nsz = struct.unpack_from('<HhHH', data, p)
                p += 8
                name = data[p:p + nsz + 1].decode('utf-8', 'replace')
                p += nsz + 1
                out.append((name, (start << 16) | off))
        return out

    def walk(self, ref=None, path=''):
        if ref is None:
            ref = self.root_inode
        ino = self.inode(ref)
        for name, cref in self.readdir(ino):
            child = self.inode(cref)
            cpath = path + '/' + name
            yield cpath, child
            if child['type'] in (1, 8):
                yield from self.walk(cref, cpath)

    def read_file(self, ino):
        out = bytearray()
        pos = ino['start']
        for bs in ino['blocks']:
            csize = bs & 0xffffff
            if csize == 0:
                out += b'\0' * self.block_size
                continue
            raw = self.rd(pos, csize)
            pos += csize
            out += raw if bs & (1 << 24) else self.decomp(raw)
        if ino['frag'] != 0xffffffff:
            fstart, fsize, _ = self.frags()[ino['frag']]
            raw = self.rd(fstart, fsize & 0xffffff)
            fdata = raw if fsize & (1 << 24) else self.decomp(raw)
            out += fdata[ino['foff']:ino['foff'] + (ino['size'] - len(out))]
        return bytes(out[:ino['size']])


def find(path):
    data = open(path, 'rb').read()
    i = 0
    while True:
        i = data.find(b'hsqs', i)
        if i < 0:
            break
        try:
            vmaj, vmin = struct.unpack_from('<HH', data, i + 28)
            comp = struct.unpack_from('<H', data, i + 20)[0]
            bused = struct.unpack_from('<Q', data, i + 40)[0]
            if (vmaj, vmin) == (4, 0):
                print('offset=%d comp=%s bytes_used=%d' % (i, COMP.get(comp), bused))
        except struct.error:
            pass
        i += 4


def main():
    cmd = sys.argv[1]
    if cmd == 'find':
        return find(sys.argv[2])
    f = open(sys.argv[2], 'rb')
    fs = Sqfs(f, int(sys.argv[3]))
    if cmd == 'list':
        for p, ino in fs.walk():
            t = ino['type']
            extra = (' -> ' + ino['target']) if t in (3, 10) else ''
            print('%2d %9s %s%s' % (t, ino.get('size', ''), p, extra))
    elif cmd == 'extract':
        outdir, rx = sys.argv[4], re.compile(sys.argv[5])
        links = []
        for p, ino in fs.walk():
            if not rx.search(p):
                continue
            t = ino['type']
            rel = os.path.normpath(p.lstrip('/'))
            if rel.startswith('..') or os.path.isabs(rel):
                continue
            dst = os.path.join(outdir, rel)
            if t in (2, 9):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as o:
                    o.write(fs.read_file(ino))
            elif t in (3, 10):
                links.append('%s -> %s' % (p, ino['target']))
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, '_symlinks.txt'), 'a') as o:
            o.write('\n'.join(links) + '\n')


if __name__ == '__main__':
    main()
