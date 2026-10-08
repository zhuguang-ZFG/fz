# 验证完整性契约（2026-10-08）

本批对应枢纽用户「继续」「先完成软件修复」。只修host验证器，不改Grbl固件或Wokwi启动判据。

## 有符号位置差

`hardware_sim/case_runner.py`支持整例与send步骤的`expect_mpos_delta: [x,y,z]`，单位mm，比较结束位置减起始位置，负号保留。向量必须恰好三个有限数字，禁止布尔/字符串/NaN/Inf，显式零向量仍检查。`eps_mm`缺省0.6，须有限非负；`idle_timeout`缺省30s，须有限正数。

整例起点在setup完成之后、inject/steps之前；步级起点在send之前。每个有断言的步骤独立取起点，不使用上一步的缓存。两端均等待Idle并从最后一份完整状态帧读取同帧有限XYZ；`wait_idle`返回的旧MPos不能配合缺坐标/WPos的Idle帧冒充新位置。无有效位置、未Idle、位移超差均返回失败；结果记录expected/actual/eps及结束MPos。

步级断言仅支持含send的步骤；用于inject-only或expect_status-only时明确失败。显式携带位置断言的async步骤会等待其完成再比对。没有该字段的旧用例不增加位置查询。运动步数仍由既有StepOracle独立核对，不能互相替代。

## trace逐项完整性

trace顶层为列表或含lines列表的对象，各行必须是对象；输入、expect、trace长度必须一致。结构/数量错误使用`trace_shape`/`trace_length`失败，不以zip截断判绿。字段错误保留原index/line/mismatches格式。

结构错误不走字段差异缩减器；缩减过程若遇结构变化，不把它当作原字段错误的更小复现。

## 金样来源身份

来源按去首尾空白、大小写归一后的完整名称匹配；可匹配文件stem或JSON的非空name，允许.json/.nc后缀。禁止双向子串匹配和空name兜底。多个文件同时命中必须报ambiguous并停止本项录制，不能按目录/glob顺序挑第一个。精确匹配到的坏JSON明确失败，无关坏JSON不影响其他精确匹配。

CLI的--only仍是用户筛选器，不作来源身份判定。无来源时的合成草稿继续明确提示人工检查setup；歧义不允许回落到合成稿。匹配到的来源保留原setup及steps。

## 启动前云配额与观察报告

2026-10-08实跑发现runner已按既定规则将串口全空的quota判为blocking=false，但observe漏列quota而追加hard失败。observe现与runner的PRE_START_CLOUD_ERRORS分类对齐；只有报告明确blocking=false的启动前资源故障才记soft。真实固件输出/超时仍由runner判阻断，blocking=true或缺失、未知错误在observe仍为hard。测试读取runner在用分类并核对两端一致。

Wokwi云配额耗尽不等于启动通过；报告保留soft与startup not verified。禁止通过把真实启动超时改为非阻断来获得host通过。

## 验证入口

```powershell
python -m unittest hardware_sim.test_mpos_delta native_sim.test_trace_shape scripts.test_golden_source -v
python -m unittest scripts.test_golden_record -v
python hardware_sim/run_hw_sim.py --start-sim --json-only --only json_move_x10_step_window
python scripts/agent_gate.py --profile standard
```

执行standard后阅读agent_observe_last。Wokwi现有保真缺口不通过时完整门禁仍fail，不能用上述单测冒充全部通过。真机/射频/纸面验收独立。
