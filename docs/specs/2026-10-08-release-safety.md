# 发布签核与门禁报告契约（2026-10-08）

用户在七项软件问题清单后要求「同意完全修复」。本批不改产品固件，不执行硬件动作。

## 发布输入与签核

- `release_honesty`总是核对报告源码SHA；显式scope签核还要求门禁时及当前两棵工作树均明确无修改。当前状态包括暂存、未暂存与未跟踪文件；Git查询失败不能当作干净。开发模式可以带脏树警告，但不能以该模式作正式签核。
- 显式scope缺失、空白、坏格式或重复字段均阻断。`features`中的`paper_path`、`bluetooth`、`ota`必须显式为布尔值；不以字符串真值或正则决定是否需要HIL。声明SHA必须为7–40位十六进制且与门禁完整SHA相符。
- JSON无需新增依赖；YAML通过PyYAML安全解析（安装`requirements-validation.txt`），不接受任意对象或重复键。缺解析器/解析失败不能回落到宽松文本扫描。
- G3/G4继续复用现有必测项集合。签核要求有效日期、操作者、版本、产品源码SHA及板型/版本信息；必测项全部pass、每项引用可读取的非空本机证据文件。相对路径可基于证据文件目录或fz根，多个不同文件命中时判歧义。自引用、示例/占位文本、缺日志、失败或跳过项不能作为已验；模板文件本身不因名称获得豁免或自动通过。
- `--allow-pending-hil`仅使证据未齐返回`ready_to_sign_pending_hil`及`hil_ok=false`；不放宽身份、scope或SIL错误。任意阻断项均影响最终verdict。缺门禁且`--strict`返回2，其余blocked返回1。
- 非阻断失败与skip层在签核报告中仍警告“未验证”；尤其Wokwi quota不等于芯片启动通过。阻断层失败不能被顶层overall=pass掩盖。

## 门禁报告生命周期

- `GateRun`使用标准库文件锁，按results目录互斥。锁文件保留，锁本身由内核管理，退出/强停自动释放；另一个进程不能改活动报告。
- 获取锁后、读取Git/导入产品模块/启动子进程前，原子发布本轮running报告。完成、异常和中断均保留同一run_id及started_at；异常/中断写fail，强停至少留下running。observe与签核都禁止把running当作完成。
- JSON使用唯一临时文件、flush/fsync和原子替换；替换失败保留上一个完整文档并清理临时文件。临时报告路径不等于发布成功。
- GRBL_ROOT缺席时明确生成product_profile与product_host两个skip；机型未知继续fail，不恢复量产纸路来通过门禁。

## 硬件用例三态

新报告有`skipped`字段，跳过时`passed=null`；通过/失败保留true/false。JSON用例、内置用例和过滤后的session元检查保持同一规则。`case_counts`统一统计passed/failed/skipped/executed/total；旧报告明确的`skipped (...)`与`session_meta_skipped`继续识别为跳过。无skip标志的null不是通过。

重复运行、输出标签、退出码、observe汇总均使用同一判定；重复运行缺报告必须失败。未跑的硬件层只能展示旧结果作历史提示，不能把旧失败计成本轮硬错误。

## 验证入口

`scripts.test_release_safety`覆盖签核负例和合法证据；`scripts.test_gate_report`覆盖早期异常、ImportError、中断、强停、锁和原子替换；`hardware_sim.test_case_outcomes`覆盖显式/旧版skip及observe。连同既有G3/G4、签核、观察和硬件测试执行，再跑量产nopaper完整standard并阅读observe。软件通过不替代Wokwi、无线、OTA或纸面验收。
