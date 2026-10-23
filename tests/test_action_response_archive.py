import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import archive_action_response as archiver
from scripts.archive_action_response import split_file,members,restore,sha,PART_BYTES


class ActionResponseArchiveTest(unittest.TestCase):
    def prepare(self,root,data=b"\x00\xff\x80a\r\n"*5):
        source=root/"raw/data.gz";source.parent.mkdir();source.write_bytes(data)
        output=root/"parts";split_file(source,output,sha(source),part_bytes=7)
        return source,output/"parts.json"

    def test_binary_bytes_roundtrip_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,index=self.prepare(root);before=source.read_bytes()
            value,paths=members(index);target=root/"restored/data.gz";result=restore(index,target)
            self.assertEqual(target.read_bytes(),before);self.assertEqual(source.read_bytes(),before)
            self.assertEqual(result["sha256"],sha(source));self.assertTrue(all(p.stat().st_size<=7 for p in paths))
            self.assertEqual(value["source_size"],len(before))

    def test_corruption_is_rejected_before_target_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);_,index=self.prepare(root);part=index.parent/"part-00000.bin"
            data=bytearray(part.read_bytes());data[0]^=1;part.write_bytes(data)
            target=root/"restored/data.gz"
            with self.assertRaisesRegex(ValueError,"checksum"):restore(index,target)
            self.assertFalse(target.exists())

    def test_reordering_and_path_escape_are_rejected(self):
        for kind in ("order","path"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);_,index=self.prepare(root);value=json.loads(index.read_text())
                if kind=="order":value["parts"][0],value["parts"][1]=value["parts"][1],value["parts"][0]
                else:value["parts"][0]["file"]="../outside.bin"
                index.write_text(json.dumps(value))
                with self.assertRaises(ValueError):members(index)

    def test_existing_original_and_invalid_source_hash_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,index=self.prepare(root);before=source.read_bytes()
            with self.assertRaises(FileExistsError):restore(index,source)
            with self.assertRaises(ValueError):split_file(source,root/"bad","0"*64)
            self.assertFalse((root/"bad").exists());self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(FileExistsError):split_file(source,source.parent/"new",sha(source))

    def test_empty_artifact_and_part_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,index=self.prepare(root,b"");restore(index,root/"empty.gz")
            self.assertEqual((root/"empty.gz").read_bytes(),b"")
            for size in (0,True,PART_BYTES+1):
                with self.assertRaises(ValueError):split_file(source,root/"invalid",sha(source),part_bytes=size)

    def test_full_pack_requires_completed_audit_and_binds_exact_source_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,_=self.prepare(root)
            identity={"experiment_run_id":"synthetic","manifest_id":"synthetic","source_git_commit":"synthetic"}
            manifest=source.parent/"manifest.json";manifest.write_text(json.dumps(identity),encoding="utf-8")
            audit={**identity,"integrity":"PASSED","episodes":4607,"environment_resets":4608,
                "api_calls":0,"memory_writes":0,"status":"COMPLETED_COMPETITIVE_FAILED",
                "artifact_sha256":{source.name:sha(source),manifest.name:sha(manifest)}}
            audit_path=root/"audit.json";audit_path.write_text(json.dumps(audit),encoding="utf-8")
            with self.assertRaises(ValueError):archiver.archive(manifest,audit_path,root/"incomplete")
            self.assertFalse((root/"incomplete").exists())
            audit["episodes"]=4608;audit_path.write_text(json.dumps(audit),encoding="utf-8")
            with patch.object(archiver,"PART_BYTES",7):
                result=archiver.archive(manifest,audit_path,root/"packed")
                restored=root/"restored/data.gz"
                index=root/"packed"/result["archives"][source.name]["index"]
                archiver.restore(index,restored)
            self.assertTrue(result["original_files_preserved"])
            self.assertEqual(result["primary_audit_sha256"],sha(audit_path))
            self.assertEqual(restored.read_bytes(),source.read_bytes())


if __name__=="__main__":unittest.main()
