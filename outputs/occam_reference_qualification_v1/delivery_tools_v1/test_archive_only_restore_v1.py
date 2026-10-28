"""No original data tree is created; only constructed ZIP/index and fresh output."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import gzip,hashlib,tempfile,zipfile
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import recover_native_archive_only_v1 as r


class ArchiveOnlyTests(TestCase):
    def fixture(self,root):
        a=gzip.compress(b'{"fixture":1}\n');b=gzip.compress(b'{"fixture":2}\n')
        data={'canonical.gz':a+b,'one.gz':a,'two.gz':b,'meta.json':b'{"constructed":true}'}
        path=root/'input.zip'
        with zipfile.ZipFile(path,'w') as archive:
            for name in ('canonical.gz','meta.json'):archive.writestr(name,data[name])
        files={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in data.items()}
        aliases={n:dict(anchor='canonical.gz',offset=o,bytes=len(data[n]),sha256=files[n]['sha256']) for n,o in (('one.gz',0),('two.gz',len(a)))}
        return path,dict(schema='OCCAM_QUALIFICATION_ZIP_ALIASES_V1',bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),files=files,aliases=aliases),data

    def test_all_files_restore_with_originals_absent_and_reads_forbidden(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target,index,data=self.fixture(root);dest=root/'restored'
            original_sha=r.b.c.sha
            def allowed_only(path):
                p=Path(path).resolve()
                if p!=target.resolve() and not p.is_relative_to(dest.resolve()):raise AssertionError('read outside new output/ZIP')
                return original_sha(path)
            with patch.object(r.b.c,'sha',side_effect=allowed_only),patch('subprocess.Popen',side_effect=AssertionError('no processes')):
                result=r.restore_zip(target,index,dest,lambda *args:None)
            self.assertFalse(result['original_raw_files_required']);self.assertFalse(result['original_raw_byte_comparison'])
            self.assertEqual(result['decoded_canonical_gzip_lines'],2)
            for n,v in data.items():self.assertEqual((dest/n).read_bytes(),v);self.assertFalse((root/n).exists())

    def test_committed_file_hash_still_required_without_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target,index,_=self.fixture(root);index['files']['meta.json']['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'original file restored'):
                r.restore_zip(target,index,root/'restored',lambda *args:None)

    def test_missing_or_changed_zip_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target,index,_=self.fixture(root);target.write_bytes(target.read_bytes()+b'x')
            with self.assertRaisesRegex(ValueError,'whole ZIP bytes'):
                r.restore_zip(target,index,root/'restored',lambda *args:None)
            self.assertFalse((root/'restored').exists())
