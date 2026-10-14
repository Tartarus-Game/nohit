"""Inspect/extract ZIP and unencrypted Godot PCK v1/v2/v3; inventory GM FORM.
Never executes packages or attempts to decrypt them. Standard library only.
Godot layout reference: godotengine/godot core/io/file_access_pack.cpp (3.3,4.6).
"""
import argparse, hashlib, json, pathlib, struct, zipfile
MAX_BYTES=512*1024*1024
MAX_FILES=100000

def safe_name(name):
    name=name.removeprefix('res://')
    p=pathlib.PurePosixPath(name)
    if not name or '\\' in name or '\x00' in name or p.is_absolute() or ':' in name or '..' in p.parts:
        raise ValueError('unsafe archive path: '+repr(name))
    return str(p)

def pck_entries(data):
    version,major,minor,patch=struct.unpack_from('<4I',data,4)
    if version==1:
        pos=84;base=0;flags=0
    elif version in (2,3):
        flags,base=struct.unpack_from('<IQ',data,20)
        if flags & ~2: raise ValueError('encrypted/sparse/unsupported PCK flags')
        pos=struct.unpack_from('<Q',data,32)[0] if version==3 else 96
    else: raise ValueError('unsupported PCK version')
    def read(fmt):
        nonlocal pos
        n=struct.calcsize(fmt)
        if pos+n>len(data):raise ValueError('truncated directory')
        out=struct.unpack_from(fmt,data,pos);pos+=n;return out
    count=read('<I')[0]
    if count>MAX_FILES:raise ValueError('too many files')
    entries=[];total=0;names=set()
    for _ in range(count):
        n=read('<I')[0]
        if n>65536 or pos+n>len(data):raise ValueError('invalid path length')
        name=safe_name(data[pos:pos+n].rstrip(b'\0').decode('utf-8'));pos+=n
        offset,size=read('<QQ');md5=read('<16s')[0]
        file_flags=read('<I')[0] if version>=2 else 0
        if file_flags:raise ValueError('encrypted/removal/delta entries unsupported')
        offset+=base;total+=size
        if offset+size>len(data) or total>MAX_BYTES:raise ValueError('invalid data range/size limit')
        if name in names:raise ValueError('duplicate path')
        names.add(name);payload=data[offset:offset+size]
        verified=md5 != bytes(16)
        if verified and hashlib.md5(payload).digest()!=md5:raise ValueError('MD5 mismatch: '+name)
        entries.append((name,payload,verified))
    return {'engine':'Godot','pack_version':version,'engine_version':f'{major}.{minor}.{patch}'},entries

def unpack(path,out=None):
    if path.stat().st_size>MAX_BYTES:raise ValueError('archive too large')
    data=path.read_bytes();entries=[]
    if data[:4]==b'GDPC':
        info,entries=pck_entries(data)
    elif zipfile.is_zipfile(path):
        info={'engine':'unknown','format':'ZIP'}
        with zipfile.ZipFile(path) as z:
            names=set();total=0
            if len(z.infolist())>MAX_FILES:raise ValueError('too many ZIP entries')
            for i in z.infolist():
                if i.is_dir():continue
                name=safe_name(i.filename);total+=i.file_size
                if name in names or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('duplicate/symlink entry')
                if total>MAX_BYTES:raise ValueError('expanded size limit')
                names.add(name);entries.append((name,z.read(i),True))
    elif data[:4]==b'FORM':
        info={'engine':'GameMaker','format':'FORM','chunks':[]};pos=8
        end=struct.unpack_from('<I',data,4)[0]+8
        if end>len(data):raise ValueError('truncated FORM')
        while pos<end:
            if pos+8>end:raise ValueError('truncated chunk header')
            tag=data[pos:pos+4].decode('ascii');size=struct.unpack_from('<I',data,pos+4)[0];pos+=8
            if pos+size>end:raise ValueError('truncated chunk')
            info['chunks'].append({'tag':tag,'offset':pos,'size':size});pos+=size
        info['note']='Chunk inventory only. No GML decompilation or YYC recovery.'
    else:raise ValueError('unknown format; embedded EXE packs are not scanned automatically')
    info['source_sha256']=hashlib.sha256(data).hexdigest()
    info['entries']=[{'path':n,'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),'archive_checksum_verified':v} for n,b,v in entries]
    if out:
        out.mkdir(parents=True,exist_ok=False)
        for name,payload,_ in entries:
            dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(payload)
        (out/'_nohit_unpack_manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
    return info
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('package',type=pathlib.Path);ap.add_argument('--extract',type=pathlib.Path);ap.add_argument('--manifest',type=pathlib.Path);a=ap.parse_args()
    result=unpack(a.package,a.extract)
    if a.manifest:a.manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='entries'},ensure_ascii=False));print('files:',len(result['entries']))
