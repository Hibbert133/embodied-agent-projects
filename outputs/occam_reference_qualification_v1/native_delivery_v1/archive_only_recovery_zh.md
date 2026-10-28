# 从归档独立恢复 NATIVE 数据

已用实际Git分片恢复全部2288个文件，并在运行时禁止读取原来的NATIVE／
QUAL记录树，读取尝试为0；无需本机原始大文件。每个规范文件与gzip成员
别名均按提交索引中的长度／SHA-256检查，158286行规范gzip又做解码秘密
扫描。此模式不与原件比较字节；另两次本地ZIP和实际Git恢复已与原件比较。

本入口复用已检查的归档算法，不改变原严格原件核对入口。3个新增工程
检查覆盖原件不存在／禁止读取、坏索引文件哈希、被改ZIP；不算科学资格。
没有新环境、策略／模型调用、拟合或在线LLM。没有实际执行完整新clone的
依赖安装测试；入口需要本仓库代码和相应既有Python依赖。

在包含这些分片的仓库提交中，从仓库根目录执行以下PowerShell示例。
目标恢复目录与收据必须尚不存在。远端使用实际归档HEAD；原科学冻结提交
或原本地数据提交编号未必存在于精简归档历史，不能拿它们代替。

```powershell
$nativeArchiveCommit = (git rev-parse HEAD).Trim()
python outputs/occam_reference_qualification_v1/delivery_tools_v1/recover_native_archive_only_v1.py --source $nativeArchiveCommit --restore C:/Research/native-restore --receipt C:/Research/native-restore-receipt.json
```

C:/Research父目录需存在，也可换成有空间的可写位置。不会覆盖已有恢复
目录；组装ZIP和恢复数据均保留。收据记录实际使用的Git对象身份、索引
哈希、原件读取护栏和完整文件数。SHA校验是记录完整性检查，不是物理／
预测／任务收益／安全保证。NATIVE只有单组，独立QUAL仍按原冻结设计执行。
