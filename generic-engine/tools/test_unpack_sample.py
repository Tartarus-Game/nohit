import importlib.util, pathlib, tempfile, struct, zipfile, hashlib, unittest
spec=importlib.util.spec_from_file_location('unpack',pathlib.Path(__file__).with_name('unpack_sample.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestUnpack(unittest.TestCase):
 def pack(self,version,payload=b'hello'):
  name=b'res://soul.gd\0\0\0';entry_size=4+len(name)+32+(4 if version>=2 else 0)
  head_size={1:84,2:96,3:128}[version];offset=head_size+4+entry_size
  head=struct.pack('<5I',0x43504447,version,3 if version==1 else 4,3 if version==1 else 6,0)
  if version==1:head+=bytes(64)
  elif version==2:head+=struct.pack('<IQ',0,0)+bytes(64)
  else:head+=struct.pack('<IQQ',2,0,128)+bytes(88)
  return head+struct.pack('<II',1,len(name))+name+struct.pack('<QQ',offset,len(payload))+hashlib.md5(payload).digest()+(bytes(4) if version>=2 else b'')+payload
 def test_versions(self):
  for version in (1,2,3):
   info,entries=m.pck_entries(self.pack(version));self.assertEqual(entries,[('soul.gd',b'hello',True)]);self.assertEqual(info['pack_version'],version)
 def test_corruption(self):
  with self.assertRaisesRegex(ValueError,'MD5'):m.pck_entries(self.pack(3)[:-1]+b'x')
 def test_truncation(self):
  with self.assertRaises(ValueError):m.pck_entries(self.pack(2)[:-3])
 def test_unsafe_paths(self):
  for name in ['../x','res://../../x','/x','a\\x','C:/x','x\0']:
   with self.assertRaises(ValueError):m.safe_name(name)
 def test_zip(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'game.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('scripts/soul.gd','safe')
   out=pathlib.Path(td)/'extract';r=m.unpack(p,out);self.assertEqual((out/'scripts/soul.gd').read_text(),'safe');self.assertEqual(len(r['entries']),1)
 def test_zip_traversal(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'bad.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('../bad','x')
   with self.assertRaises(ValueError):m.unpack(p,pathlib.Path(td)/'out')
 def test_form(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'data.win';p.write_bytes(b'FORM'+struct.pack('<I',11)+b'CODE'+struct.pack('<I',3)+b'abc')
   self.assertEqual(m.unpack(p)['chunks'][0]['tag'],'CODE')
if __name__=='__main__':unittest.main()
