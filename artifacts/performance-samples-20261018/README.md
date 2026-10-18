# 全量 CSV 性能证据

对应 `docs/optimization-samples-20261018.md`。`release` 为最终统一参数运行；repeat-2/3 只复测 29 个快例；wide 为单独的加宽 branch1。

`inputs.zip` 只有捕获入口、精确时钟、CSV 和预处理记录，没有答案或世界缓存。`witnesses/` 与 `native/` 中的轨迹仅作验收证据，不被批量求解工具读取。`native-final-revalidation.json` 是对已在原 C2 运行过的输入字作最终独立模型复验，非新的性能测量。

主表安装构建时间另列。首次从源码启动另见 source-cold.json。unknown 和 missing 不是通过。
